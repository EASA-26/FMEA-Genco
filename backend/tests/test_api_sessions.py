"""Session store and login rate limiter (unit level)."""
from __future__ import annotations

import threading

from backend.auth.service import LoginRateLimiter
from backend.sessions.store import SessionStore
from backend.tests.test_api_support import make_report


class FakeClock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# --------------------------------------------------------------------------- #
# SessionStore
# --------------------------------------------------------------------------- #
def test_create_get_destroy():
    store = SessionStore(idle_minutes=60, max_sessions=10)
    session = store.create("SYNTHETIC user")
    assert len(session.token) >= 43  # token_urlsafe(32)
    assert store.get(session.token) is session
    assert store.get("not-a-token") is None
    assert store.get(None) is None
    assert store.destroy(session.token) is True
    assert store.get(session.token) is None
    assert store.destroy(session.token) is False
    assert len(store) == 0


def test_tokens_are_unique():
    store = SessionStore(idle_minutes=60, max_sessions=500)
    tokens = {store.create("u").token for _ in range(300)}
    assert len(tokens) == 300


def test_idle_timeout_and_activity_extends_it():
    clock = FakeClock()
    store = SessionStore(idle_minutes=10, max_sessions=10, clock=clock)
    session = store.create("u")

    clock.advance(9 * 60)
    assert store.get(session.token) is session      # used: idle timer restarts
    clock.advance(10 * 60)
    assert store.get(session.token) is session      # exactly the limit is still fine
    clock.advance(10 * 60 + 1)
    assert store.get(session.token) is None         # idle too long
    assert len(store) == 0


def test_expired_session_loses_its_report():
    clock = FakeClock()
    store = SessionStore(idle_minutes=1, max_sessions=10, clock=clock)
    session = store.create("u")
    store.set_report(session, make_report())
    clock.advance(61)
    assert store.get(session.token) is None
    assert session.report is None and session.pdf_bytes is None and not session.alive


def test_lru_eviction_drops_least_recently_used():
    clock = FakeClock()
    store = SessionStore(idle_minutes=60, max_sessions=2, clock=clock)
    first = store.create("first")
    clock.advance(1)
    second = store.create("second")
    clock.advance(1)
    assert store.get(first.token) is first           # first is now the most recent
    clock.advance(1)
    third = store.create("third")

    assert len(store) == 2
    assert store.get(second.token) is None           # least recently used was evicted
    assert store.get(first.token) is first
    assert store.get(third.token) is third
    assert second.report is None and not second.alive


def test_expired_sessions_are_purged_before_evicting_active_ones():
    clock = FakeClock()
    store = SessionStore(idle_minutes=1, max_sessions=2, clock=clock)
    stale = store.create("stale")
    clock.advance(50)
    active = store.create("active")
    clock.advance(20)                                # stale is now idle 70 s, active 20 s
    newcomer = store.create("newcomer")
    assert store.get(active.token) is active
    assert store.get(newcomer.token) is newcomer
    assert store.get(stale.token) is None


def test_purge_expired_counts_removed():
    clock = FakeClock()
    store = SessionStore(idle_minutes=1, max_sessions=10, clock=clock)
    store.create("a")
    store.create("b")
    clock.advance(61)
    store_c = store.create("c")
    assert store.purge_expired() == 0                # already purged by create()
    clock.advance(61)
    assert store.purge_expired() == 1
    assert store.get(store_c.token) is None


def test_report_replacement_clears_pdf_cache_and_rejects_stale_pdf():
    store = SessionStore(idle_minutes=60, max_sessions=10)
    session = store.create("u")
    store.set_report(session, make_report(station="SYNTHETIC A"))
    report, version, pdf = store.snapshot(session)
    assert report.station == "SYNTHETIC A" and pdf is None

    assert store.cache_pdf(session, version, b"%PDF A") is True
    assert store.snapshot(session).pdf_bytes == b"%PDF A"

    store.set_report(session, make_report(station="SYNTHETIC B"))
    assert store.snapshot(session).pdf_bytes is None
    # A render of the old report finishing late must not be cached for the new one.
    assert store.cache_pdf(session, version, b"%PDF A late") is False
    assert store.snapshot(session).pdf_bytes is None

    store.clear_report(session)
    assert store.get_report(session) is None


def test_destroyed_session_accepts_no_new_data():
    store = SessionStore(idle_minutes=60, max_sessions=10)
    session = store.create("u")
    store.set_report(session, make_report())
    version = store.snapshot(session).version
    store.destroy(session.token)
    assert session.report is None
    store.set_report(session, make_report())
    assert session.report is None
    assert store.cache_pdf(session, version, b"%PDF") is False


def test_store_is_thread_safe_under_concurrent_use():
    store = SessionStore(idle_minutes=60, max_sessions=50)
    errors: list[BaseException] = []

    def worker():
        try:
            for _ in range(200):
                session = store.create("u")
                store.set_report(session, make_report())
                store.get(session.token)
                store.snapshot(session)
                if len(session.token) % 2:
                    store.destroy(session.token)
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert len(store) <= 50


def test_per_user_limit_ends_that_users_oldest_session_only():
    clock = FakeClock()
    store = SessionStore(idle_minutes=60, max_sessions=10, clock=clock, max_sessions_per_user=2)
    other = store.create("SYNTHETIC other")
    clock.advance(1)
    first = store.create("SYNTHETIC user")
    clock.advance(1)
    second = store.create("SYNTHETIC user")
    clock.advance(1)
    assert store.get(first.token) is first           # first is now more recent than second
    clock.advance(1)
    third = store.create("SYNTHETIC user")

    assert store.get(second.token) is None and not second.alive
    assert store.get(first.token) is first and store.get(third.token) is third
    assert store.get(other.token) is other
    for _ in range(20):
        store.create("SYNTHETIC user")
    assert store.get(other.token) is other
    assert len(store) == 3


def test_invalid_limits_are_clamped():
    store = SessionStore(idle_minutes=0, max_sessions=0)
    first = store.create("a")
    second = store.create("b")
    assert len(store) == 1
    assert store.get(first.token) is None and store.get(second.token) is second


# --------------------------------------------------------------------------- #
# LoginRateLimiter
# --------------------------------------------------------------------------- #
def test_limiter_blocks_after_five_attempts_within_window():
    clock = FakeClock()
    limiter = LoginRateLimiter(clock=clock)
    assert LoginRateLimiter.key_for("Admin ", "10.0.0.1") == LoginRateLimiter.key_for("admin", "10.0.0.1")
    for _ in range(5):
        assert limiter.begin_attempt("Admin ", "10.0.0.1") == 0
        clock.advance(10)
    wait = limiter.begin_attempt("admin", "10.0.0.1")
    assert 0 < wait <= 300

    # Other usernames and other clients are counted separately.
    assert limiter.begin_attempt("admin", "10.0.0.2") == 0
    assert limiter.begin_attempt("other", "10.0.0.1") == 0

    # Once the first failure is older than 5 minutes, one more attempt is allowed.
    clock.advance(300 - 50 + 1)
    assert limiter.begin_attempt("admin", "10.0.0.1") == 0
    assert limiter.begin_attempt("admin", "10.0.0.1") > 0


def test_limiter_reset_clears_failures():
    limiter = LoginRateLimiter(clock=FakeClock())
    for _ in range(5):
        limiter.begin_attempt("admin", "c")
    assert limiter.begin_attempt("admin", "c") > 0
    limiter.reset("ADMIN", "c")
    assert limiter.begin_attempt("admin", "c") == 0


def test_limiter_blocks_a_client_trying_many_usernames():
    clock = FakeClock()
    limiter = LoginRateLimiter(clock=clock, max_client_failures=50)
    for n in range(50):
        assert limiter.begin_attempt(f"SYNTHETIC-user-{n}", "10.0.0.9") == 0
    # A new username from the same client is refused; other clients are not affected.
    assert limiter.begin_attempt("SYNTHETIC-user-new", "10.0.0.9") > 0
    assert limiter.begin_attempt("SYNTHETIC-user-new", "10.0.0.10") == 0
    # A successful sign-in does not clear the per-client count.
    limiter.reset("SYNTHETIC-user-0", "10.0.0.9")
    assert limiter.begin_attempt("SYNTHETIC-user-0", "10.0.0.9") > 0
    clock.advance(5 * 60)
    assert limiter.begin_attempt("SYNTHETIC-user-new", "10.0.0.9") == 0


def test_limiter_memory_is_bounded():
    limiter = LoginRateLimiter(clock=FakeClock(), max_keys=100)
    for n in range(1000):
        limiter.begin_attempt("SYNTHETIC-user-" + "x" * 10_000 + str(n), f"10.0.{n // 250}.{n % 250}")
    assert len(limiter._accounts.entries) == 100
    assert len(limiter._clients.entries) == 100
    assert all(len(key) <= 200 for key in limiter._accounts.entries)
