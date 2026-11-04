"""One-time use while an upload is still being read.

A discard (DELETE /api/workbook, which the page sends when it is left, or a
sign-out), a newer upload, or the browser giving up (Cancel, closing the tab)
while the server is still reading a workbook means that upload's report must
not be kept. All data is SYNTHETIC; the parser is `FakeServices`.
"""
from __future__ import annotations

import threading
import time

import pytest
from starlette.requests import Request

from backend.api.routes_report import MSG_UPLOAD_SUPERSEDED
from backend.sessions.store import SessionStore
from backend.tests.test_api_support import FakeServices, login, make_client, make_report, upload

WAIT = 10


class SlowServices(FakeServices):
    """`build_report` waits for the test to release it (only for data starting with b"SLOW")."""

    def __init__(self) -> None:
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def build_report(self, data: bytes, filename: str):
        if data.startswith(b"SLOW"):
            self.entered.set()
            assert self.release.wait(WAIT), "the test never released the upload"
        return super().build_report(data, filename)


def _start_slow_upload(client, services, filename="SYNTHETIC_slow.xlsx"):
    result = {}

    def run():
        result["response"] = upload(client, b"SLOW SYNTHETIC workbook", filename)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert services.entered.wait(WAIT), "the upload never reached the parser"
    return thread, result


def _finish(services, thread, result):
    services.release.set()
    thread.join(WAIT)
    assert not thread.is_alive()
    return result["response"]


@pytest.fixture
def signed_in():
    services = SlowServices()
    client = make_client(services=services)
    assert login(client).status_code == 200
    return client, services


def test_discard_while_reading_keeps_nothing(signed_in):
    client, services = signed_in
    thread, result = _start_slow_upload(client, services)
    # What the page sends when it is left while the server reads the workbook.
    assert client.delete("/api/workbook").status_code == 204
    response = _finish(services, thread, result)
    assert response.status_code == 409
    assert response.json() == {"detail": MSG_UPLOAD_SUPERSEDED}
    assert client.get("/api/report").status_code == 404
    assert client.get("/api/report/pdf").status_code == 404


def test_discard_while_reading_also_drops_the_previous_report(signed_in):
    client, services = signed_in
    assert upload(client, filename="SYNTHETIC_first.xlsx").status_code == 200
    thread, result = _start_slow_upload(client, services)
    assert client.delete("/api/workbook").status_code == 204
    assert _finish(services, thread, result).status_code == 409
    assert client.get("/api/report").status_code == 404


def test_newer_upload_wins_over_one_still_being_read(signed_in):
    client, services = signed_in
    thread, result = _start_slow_upload(client, services, "SYNTHETIC_older.xlsx")
    newer = upload(client, filename="SYNTHETIC_newer.xlsx")
    assert newer.status_code == 200
    assert _finish(services, thread, result).status_code == 409
    assert client.get("/api/report").json()["source_filename"] == "SYNTHETIC_newer.xlsx"


def test_upload_without_interference_is_kept(signed_in):
    client, services = signed_in
    thread, result = _start_slow_upload(client, services)
    response = _finish(services, thread, result)
    assert response.status_code == 200
    assert client.get("/api/report").json()["source_filename"] == "SYNTHETIC_slow.xlsx"


def test_failed_upload_keeps_the_previous_report():
    client = make_client()
    assert login(client).status_code == 200
    assert upload(client, filename="SYNTHETIC_first.xlsx").status_code == 200
    assert upload(client, b"NOT-A-WORKBOOK", "SYNTHETIC_bad.xlsx").status_code == 400
    assert client.get("/api/report").json()["source_filename"] == "SYNTHETIC_first.xlsx"


def test_browser_that_gave_up_keeps_the_previous_report(monkeypatch):
    client = make_client()
    assert login(client).status_code == 200
    assert upload(client, filename="SYNTHETIC_first.xlsx").status_code == 200

    async def gone(self) -> bool:
        return True

    # Cancel or a closed tab: the connection is gone by the time the workbook has been read.
    monkeypatch.setattr(Request, "is_disconnected", gone)
    response = upload(client, filename="SYNTHETIC_cancelled.xlsx")
    assert response.status_code == 409
    monkeypatch.undo()
    # The page that cancelled may still show the first report, so the server keeps it.
    assert client.get("/api/report").json()["source_filename"] == "SYNTHETIC_first.xlsx"


def test_sign_out_while_reading_keeps_nothing(signed_in):
    client, services = signed_in
    store = client.app.state.sessions
    thread, result = _start_slow_upload(client, services)
    assert client.post("/api/auth/logout").status_code in (200, 204)
    assert _finish(services, thread, result).status_code == 409
    assert len(store) == 0


# --------------------------------------------------------------------------- #
# SessionStore
# --------------------------------------------------------------------------- #
def test_store_keeps_only_the_latest_upload():
    store = SessionStore(idle_minutes=60, max_sessions=10, clock=time.monotonic)
    session = store.create("SYNTHETIC-user")
    first = store.begin_upload(session)
    second = store.begin_upload(session)
    assert store.set_report(session, make_report(station="SYNTHETIC first"), upload=first) is False
    assert store.get_report(session) is None
    assert store.set_report(session, make_report(station="SYNTHETIC second"), upload=second) is True
    assert store.get_report(session).station == "SYNTHETIC second"


def test_store_clear_report_cancels_an_upload_in_progress():
    store = SessionStore(idle_minutes=60, max_sessions=10)
    session = store.create("SYNTHETIC-user")
    pending = store.begin_upload(session)
    store.clear_report(session)
    assert store.set_report(session, make_report(), upload=pending) is False
    assert store.get_report(session) is None


def test_store_set_report_without_upload_token_still_works():
    store = SessionStore(idle_minutes=60, max_sessions=10)
    session = store.create("SYNTHETIC-user")
    assert store.set_report(session, make_report()) is True
    assert store.get_report(session) is not None
    store.destroy(session.token)
    assert store.set_report(session, make_report()) is False
