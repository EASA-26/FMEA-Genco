"""In-memory, server-side session store.

Each signed-in browser gets a random token (kept in an HttpOnly cookie) that
maps to a `Session` holding the current `Report` and the PDF rendered from it.
Nothing is written to disk. The app runs a single uvicorn worker, so one
process-wide store is enough; it is shared between the event loop and the
threadpool, hence the lock.

Sessions end when they are destroyed (sign out), when they are idle for longer
than ``idle_minutes``, or when the store is full and they are the least
recently used.
"""
from __future__ import annotations

import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import NamedTuple

from backend.report.models import Report

TOKEN_BYTES = 32


@dataclass(eq=False)
class Session:
    token: str
    user_name: str
    created_at: float
    last_seen: float
    report: Report | None = None
    # Bumped on every report change so a PDF rendered from an older report is
    # never cached against a newer one.
    report_version: int = 0
    pdf_bytes: bytes | None = None
    # Bumped when an upload starts and when the report is discarded. An upload
    # stores its report only if nothing newer happened meanwhile, so a discard
    # (sign-out, leaving the page) or a newer upload wins over an upload that
    # was still being read.
    upload_generation: int = 0
    alive: bool = True
    # Serialises PDF rendering per session (preview and download clicked
    # together render once).
    pdf_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


class ReportSnapshot(NamedTuple):
    report: Report | None
    version: int
    pdf_bytes: bytes | None


class SessionStore:
    def __init__(
        self,
        idle_minutes: float,
        max_sessions: int,
        clock: Callable[[], float] = time.monotonic,
        max_sessions_per_user: int | None = None,
    ) -> None:
        self._idle_seconds = max(float(idle_minutes), 1 / 60) * 60.0
        self._max_sessions = max(int(max_sessions), 1)
        # Optional limit per user name. When a user starts one more session than
        # this, their own least recently used session ends, so one user (or a
        # browser that drops cookies) cannot push everybody else's sessions out.
        self._max_per_user = None if max_sessions_per_user is None else max(int(max_sessions_per_user), 1)
        self._clock = clock
        self._lock = threading.RLock()
        # Ordered from least to most recently used.
        self._sessions: OrderedDict[str, Session] = OrderedDict()

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def create(self, user_name: str) -> Session:
        """Start a new session, evicting expired and least-recently-used ones."""
        now = self._clock()
        with self._lock:
            self._purge_expired_locked(now)
            if self._max_per_user is not None:
                own = [token for token, s in self._sessions.items() if s.user_name == user_name]
                for token in own[: max(0, len(own) - self._max_per_user + 1)]:  # least recent first
                    self._retire(self._sessions.pop(token))
            while len(self._sessions) >= self._max_sessions:
                _, evicted = self._sessions.popitem(last=False)
                self._retire(evicted)
            token = secrets.token_urlsafe(TOKEN_BYTES)
            while token in self._sessions:  # practically impossible, but cheap to rule out
                token = secrets.token_urlsafe(TOKEN_BYTES)
            session = Session(token=token, user_name=user_name, created_at=now, last_seen=now)
            self._sessions[token] = session
            return session

    def get(self, token: str | None) -> Session | None:
        """Return the live session for ``token`` and mark it as used, or None."""
        if not token:
            return None
        now = self._clock()
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return None
            if self._is_expired(session, now):
                del self._sessions[token]
                self._retire(session)
                return None
            session.last_seen = now
            self._sessions.move_to_end(token)
            return session

    def destroy(self, token: str | None) -> bool:
        """End a session and discard its report and PDF. True if it existed."""
        if not token:
            return False
        with self._lock:
            session = self._sessions.pop(token, None)
            if session is None:
                return False
            self._retire(session)
            return True

    def purge_expired(self) -> int:
        """Remove every idle-expired session; returns how many were removed."""
        with self._lock:
            return self._purge_expired_locked(self._clock())

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)

    # ------------------------------------------------------------------ #
    # Report and PDF cache
    # ------------------------------------------------------------------ #
    def begin_upload(self, session: Session) -> int:
        """Mark the start of an upload; pass the result to `set_report`."""
        with self._lock:
            session.upload_generation += 1
            return session.upload_generation

    def set_report(self, session: Session, report: Report, upload: int | None = None) -> bool:
        """Replace the session's report; the cached PDF is discarded.

        With ``upload`` (from `begin_upload`), the report is stored only if no
        newer upload started and the report was not discarded since. Returns
        whether it was stored.
        """
        with self._lock:
            if not session.alive:
                return False
            if upload is not None and upload != session.upload_generation:
                return False
            session.report = report
            session.report_version += 1
            session.pdf_bytes = None
            return True

    def clear_report(self, session: Session) -> None:
        """Discard the report and PDF; an upload still being read is not stored."""
        with self._lock:
            session.report = None
            session.report_version += 1
            session.pdf_bytes = None
            session.upload_generation += 1

    def get_report(self, session: Session) -> Report | None:
        with self._lock:
            return session.report

    def snapshot(self, session: Session) -> ReportSnapshot:
        """Consistent view of report, version and cached PDF."""
        with self._lock:
            return ReportSnapshot(session.report, session.report_version, session.pdf_bytes)

    def cache_pdf(self, session: Session, version: int, pdf_bytes: bytes) -> bool:
        """Cache a PDF rendered from report ``version``; ignored if the report changed."""
        with self._lock:
            if not session.alive or session.report_version != version:
                return False
            session.pdf_bytes = pdf_bytes
            return True

    # ------------------------------------------------------------------ #
    # Internals (call with the lock held)
    # ------------------------------------------------------------------ #
    def _is_expired(self, session: Session, now: float) -> bool:
        return now - session.last_seen > self._idle_seconds

    def _purge_expired_locked(self, now: float) -> int:
        removed = 0
        # Least recently used first, so stop at the first session still active.
        while self._sessions:
            token, session = next(iter(self._sessions.items()))
            if not self._is_expired(session, now):
                break
            del self._sessions[token]
            self._retire(session)
            removed += 1
        return removed

    @staticmethod
    def _retire(session: Session) -> None:
        # Drop the data straight away; a request still holding the object
        # cannot store anything new into it.
        session.alive = False
        session.report = None
        session.pdf_bytes = None
        session.report_version += 1
        session.upload_generation += 1
