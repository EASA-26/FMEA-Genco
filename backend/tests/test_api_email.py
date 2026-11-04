"""POST /api/report/email ("Email the PDF" through Outlook) and the "features"
flag of /api/auth/me and /api/auth/login.

Outlook and PowerShell are never started: every app gets an Outlook launcher
with a `FakeRunner`. All data is SYNTHETIC.
"""
from __future__ import annotations

import json
import logging
import subprocess
import threading

import pytest
from fastapi.testclient import TestClient

from backend.api.routes_report import (
    MSG_EMAIL_UNAVAILABLE,
    MSG_EXPORT_BLOCKED,
    MSG_NO_REPORT,
    MSG_OUTLOOK_BUSY,
    MSG_OUTLOOK_FAILED,
    MSG_PDF_FAILED,
)
from backend.auth.service import MSG_NOT_SIGNED_IN
from backend.mail import outlook as outlook_module
from backend.mail.outlook import (
    ENV_ATTACHMENT,
    ENV_INTRO_HTML,
    ENV_SUBJECT,
    ENV_TO,
    MSG_RECIPIENTS_TOO_LONG,
    MSG_TOO_MANY_RECIPIENTS,
    POWERSHELL_SCRIPT,
    powershell_command,
    run_powershell,
)
from backend.main import create_app
from backend.tests.test_api_support import (
    MISSING_DIST,
    FakeRunner,
    FakeServices,
    login,
    make_client,
    make_outlook,
    make_report,
    make_settings,
    upload,
)

EMAIL_PATH = "/api/report/email"
ATTACHMENT = "FMEA_Report_SYNTHETIC_Station_2026-01-15.pdf"
RECIPIENTS = ["SYNTHETIC.one@example.com", "synthetic.two@example.org"]
WHO = {"X-Forwarded-Email": "SYNTHETIC.engineer@example.com"}


def _client(settings=None, runner=None, services=None, platform="win32", lock=None):
    services = services if services is not None else FakeServices()
    runner = runner if runner is not None else FakeRunner()
    client = make_client(settings, services, outlook=make_outlook(runner, platform=platform, lock=lock))
    return client, services, runner


def _ready(settings=None, runner=None, services=None, platform="win32", lock=None, report=None):
    """Signed in, with an uploaded (exportable unless ``report`` says otherwise) workbook."""
    client, services, runner = _client(settings, runner, services, platform, lock)
    assert login(client).status_code == 200
    if report is not None:
        services.next_report = report
    assert upload(client).status_code == 200
    return client, services, runner


def _email(client, to="; ".join(RECIPIENTS), **kwargs):
    return client.post(EMAIL_PATH, json={"to": to}, **kwargs)


def _assert_removed(call) -> None:
    folder = call.attachment.parent
    assert folder.name.startswith("fmea-mail-") and not folder.exists()


# --------------------------------------------------------------------------- #
# Success
# --------------------------------------------------------------------------- #
def test_email_opens_outlook_with_the_pdf_attached():
    client, services, runner = _ready()
    response = _email(client, to=" SYNTHETIC.one@example.com;synthetic.two@example.org, SYNTHETIC.ONE@example.com ")
    assert response.status_code == 200
    assert response.json() == {"status": "opened", "recipients": RECIPIENTS, "attachment": ATTACHMENT}
    assert response.headers["cache-control"] == "no-store"

    [call] = runner.calls
    assert call.args == powershell_command() and call.args[-1] is POWERSHELL_SCRIPT
    assert call.env[ENV_TO] == "SYNTHETIC.one@example.com; synthetic.two@example.org"
    assert call.env[ENV_SUBJECT] == "FMEA Report - SYNTHETIC Station - 15 January 2026"
    assert call.env[ENV_INTRO_HTML] == (
        "Hello,<br><br>Please find attached the Failure Mode Effect Analysis (FMEA) report for "
        "<b>SYNTHETIC Station</b> (Date of Analysis: 15 January 2026).<br><br>"
    )
    assert call.env[ENV_ATTACHMENT] == str(call.attachment)
    assert call.attachment.name == ATTACHMENT
    _assert_removed(call)

    # The attached file is exactly the PDF the preview and download serve.
    assert call.attachment_bytes == client.get("/api/report/pdf?download=1").content
    assert services.render_calls == 1


def test_email_reuses_the_pdf_already_rendered_for_the_preview():
    client, services, runner = _ready()
    preview = client.get("/api/report/pdf")
    assert services.render_calls == 1
    assert _email(client).status_code == 200
    assert _email(client).status_code == 200
    assert services.render_calls == 1
    assert [call.attachment_bytes for call in runner.calls] == [preview.content, preview.content]


@pytest.mark.parametrize("body", [{"to": ""}, {"to": "  ;\n, "}, {}])
def test_email_without_recipients_leaves_them_to_outlook(body):
    client, _, runner = _ready()
    response = client.post(EMAIL_PATH, json=body)
    assert response.status_code == 200
    assert response.json() == {"status": "opened", "recipients": [], "attachment": ATTACHMENT}
    assert runner.calls[0].env[ENV_TO] == ""


def test_email_subject_and_intro_without_station_or_date():
    report = make_report(station="  ").model_copy(update={"analysis_date": None, "analysis_date_text": ""})
    client, _, runner = _ready(report=report)
    assert _email(client).status_code == 200
    env = runner.calls[0].env
    assert env[ENV_SUBJECT] == "FMEA Report"
    assert env[ENV_INTRO_HTML] == (
        "Hello,<br><br>Please find attached the Failure Mode Effect Analysis (FMEA) report.<br><br>"
    )


def test_email_intro_escapes_workbook_text():
    report = make_report(station='<img src=x onerror=alert(1)> SYNTHETIC & "Co"')
    client, _, runner = _ready(report=report)
    assert _email(client).status_code == 200
    env = runner.calls[0].env
    assert "<img" not in env[ENV_INTRO_HTML]
    assert "<b>&lt;img src=x onerror=alert(1)&gt; SYNTHETIC &amp; &quot;Co&quot;</b>" in env[ENV_INTRO_HTML]
    # The subject is plain text, shown as typed.
    assert env[ENV_SUBJECT] == 'FMEA Report - <img src=x onerror=alert(1)> SYNTHETIC & "Co" - 15 January 2026'
    assert all("SYNTHETIC" not in arg for arg in runner.calls[0].args)


def test_email_attachment_name_is_safe_for_windows():
    report = make_report(pdf_filename='FMEA Report "SYNTHETIC" A/B:C.pdf')
    client, _, runner = _ready(report=report)
    response = _email(client)
    assert response.status_code == 200
    assert response.json()["attachment"] == "FMEA Report _SYNTHETIC_ A_B_C.pdf"
    assert runner.calls[0].attachment.name == "FMEA Report _SYNTHETIC_ A_B_C.pdf"


def test_email_in_databricks_mode_when_forced_on():
    settings = make_settings(auth_mode="databricks", host="0.0.0.0", outlook_email="on")
    client, _, runner = _client(settings)
    assert upload(client, headers=WHO).status_code == 200
    response = _email(client, headers=WHO)
    assert response.status_code == 200
    assert len(runner.calls) == 1


# --------------------------------------------------------------------------- #
# Recipients refused (400) and malformed bodies (422)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "to,bad",
    [
        ("SYNTHETIC-no-at-sign", "SYNTHETIC-no-at-sign"),
        ("ok@example.com; synthetic@localhost", "synthetic@localhost"),
        ("ok@example.com, <synthetic@example.com>", "<synthetic@example.com>"),
        ('"synthetic"@example.com', '"synthetic"@example.com'),
        ("synthetic@@example.com", "synthetic@@example.com"),
    ],
)
def test_email_invalid_address_is_named(to, bad):
    client, services, runner = _ready()
    response = _email(client, to=to)
    assert response.status_code == 400
    assert response.json() == {"detail": f'"{bad}" is not a valid email address. Check it and try again.'}
    assert runner.calls == [] and services.render_calls == 0


def test_email_more_than_twenty_recipients():
    client, _, runner = _ready()
    addresses = [f"synthetic{n}@example.com" for n in range(21)]
    response = _email(client, to="; ".join(addresses))
    assert response.status_code == 400
    assert response.json() == {"detail": MSG_TOO_MANY_RECIPIENTS}
    assert _email(client, to="; ".join(addresses[:20])).status_code == 200
    assert len(runner.calls) == 1


def test_email_recipient_text_too_long():
    client, _, runner = _ready()
    response = _email(client, to="synthetic@example.com" + " " * 2000)
    assert response.status_code == 400
    assert response.json() == {"detail": MSG_RECIPIENTS_TOO_LONG}
    assert runner.calls == []


@pytest.mark.parametrize(
    "content",
    [json.dumps({"to": 5}), json.dumps({"to": None}), json.dumps({"to": ["a@example.com"]}), json.dumps(["x"]), "not json"],
)
def test_email_malformed_body_is_plain_422(content):
    client, _, runner = _ready()
    response = client.post(EMAIL_PATH, content=content, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str) and "loc" not in response.text
    assert runner.calls == []


def test_email_body_size_is_limited():
    client, _, runner = _ready()
    response = client.post(
        EMAIL_PATH, content=json.dumps({"to": "x" * 100_000}), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert runner.calls == []


# --------------------------------------------------------------------------- #
# No report (404), report with errors (409), render failure (500)
# --------------------------------------------------------------------------- #
def test_email_before_upload_is_404():
    client, services, runner = _client()
    assert login(client).status_code == 200
    response = _email(client)
    assert response.status_code == 404
    assert response.json() == {"detail": MSG_NO_REPORT}
    assert runner.calls == [] and services.render_calls == 0


def test_email_after_the_workbook_is_discarded_is_404():
    client, _, runner = _ready()
    assert client.delete("/api/workbook").status_code == 204
    response = _email(client)
    assert response.status_code == 404
    assert response.json() == {"detail": MSG_NO_REPORT}
    assert runner.calls == []


def test_email_report_of_another_session_is_never_used():
    client, _, runner = _ready()
    other = TestClient(client.app)                # another browser, its own session
    assert login(other).status_code == 200
    assert _email(other).status_code == 404
    assert runner.calls == []
    assert _email(client).status_code == 200


def test_email_when_report_has_errors_is_409():
    client, services, runner = _ready(report=make_report(errors=2))
    response = _email(client)
    assert response.status_code == 409
    assert response.json() == {"detail": MSG_EXPORT_BLOCKED, "error_count": 2}
    assert runner.calls == [] and services.render_calls == 0


def test_email_when_pdf_cannot_be_rendered_is_500():
    services = FakeServices()
    services.render_error = RuntimeError("SYNTHETIC renderer internals")
    client, _, runner = _ready(services=services)
    response = _email(client)
    assert response.status_code == 500
    assert response.json() == {"detail": MSG_PDF_FAILED}
    assert "renderer" not in response.text
    assert runner.calls == []


# --------------------------------------------------------------------------- #
# Not available (501)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "platform,settings",
    [
        ("linux", make_settings()),
        ("SYNTHETIC-os", make_settings(outlook_email="on")),
        ("win32", make_settings(outlook_email="off")),
        ("win32", make_settings(host="0.0.0.0")),
    ],
    ids=["linux", "not-windows-forced-on", "windows-off", "windows-shared-host"],
)
def test_email_unavailable_is_501(platform, settings):
    client, services, runner = _ready(settings=settings, platform=platform)
    for to in ("; ".join(RECIPIENTS), "SYNTHETIC-not-an-address"):
        response = _email(client, to=to)
        assert response.status_code == 501
        assert response.json() == {"detail": MSG_EMAIL_UNAVAILABLE}
    assert runner.calls == [] and services.render_calls == 0


def test_new_outlook_in_use_turns_drafts_off_for_me_and_email():
    """The "New Outlook" toggle is on (or classic Outlook is missing): the browser is told
    drafts are off (it offers download + new email instead) and the endpoint answers 501
    at once, without starting PowerShell and waiting for Windows to time out."""
    services, runner = FakeServices(), FakeRunner()
    client = make_client(None, services, outlook=make_outlook(runner, platform="win32", classic_ready=False))
    signed_in = login(client)
    assert signed_in.status_code == 200
    assert signed_in.json()["features"] == {"outlook_email": False}
    assert client.get("/api/auth/me").json()["features"] == {"outlook_email": False}
    assert upload(client).status_code == 200
    response = _email(client)
    assert response.status_code == 501
    assert response.json() == {"detail": MSG_EMAIL_UNAVAILABLE}
    assert runner.calls == [] and services.render_calls == 0


def test_email_unavailable_in_databricks_mode_by_default():
    client, _, runner = _client(make_settings(auth_mode="databricks", host="0.0.0.0"))
    assert upload(client, headers=WHO).status_code == 200
    response = _email(client, headers=WHO)
    assert response.status_code == 501
    assert response.json() == {"detail": MSG_EMAIL_UNAVAILABLE}
    assert runner.calls == []


# --------------------------------------------------------------------------- #
# Outlook failures (502)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "runner",
    [
        FakeRunner(returncode=1, stderr="SYNTHETIC Outlook is not installed"),
        FakeRunner(error=subprocess.TimeoutExpired(["SYNTHETIC"], 120)),
        FakeRunner(error=FileNotFoundError("SYNTHETIC powershell.exe")),
    ],
    ids=["exit-1", "timeout", "powershell-missing"],
)
def test_email_outlook_failure_is_502_and_cleans_up(runner):
    client, _, _ = _ready(runner=runner)
    response = _email(client)
    assert response.status_code == 502
    assert response.json() == {"detail": MSG_OUTLOOK_FAILED}
    assert "SYNTHETIC" not in response.text
    _assert_removed(runner.calls[0])

    # A failure does not leave the launch lock taken.
    runner.error, runner.returncode = None, 0
    assert _email(client).status_code == 200


def test_unexpected_launcher_error_is_plain_500_and_cleans_up():
    runner = FakeRunner(error=RuntimeError("SYNTHETIC unexpected internals"))
    client, services, _ = _client(runner=runner)
    client = TestClient(client.app, raise_server_exceptions=False)
    assert login(client).status_code == 200
    assert upload(client).status_code == 200
    response = _email(client)
    assert response.status_code == 500
    assert "internals" not in response.text
    _assert_removed(runner.calls[0])
    assert not client.app.state.outlook.lock.locked()


# --------------------------------------------------------------------------- #
# One launch at a time (429)
# --------------------------------------------------------------------------- #
def test_email_while_outlook_is_still_opening_is_429():
    client, _, runner = _ready()
    lock = client.app.state.outlook.lock
    assert lock.acquire(blocking=False)
    try:
        response = _email(client)
        assert response.status_code == 429
        assert response.json() == {"detail": MSG_OUTLOOK_BUSY}
    finally:
        lock.release()
    assert runner.calls == []
    assert _email(client).status_code == 200


def test_concurrent_launch_from_another_session_is_429():
    entered, release = threading.Event(), threading.Event()

    def block():
        entered.set()
        assert release.wait(10)

    runner = FakeRunner(on_run=block)
    client_a, _, _ = _client(make_settings(auth_mode="databricks", outlook_email="on"), runner=runner)
    first = {"X-Forwarded-Email": "SYNTHETIC.first@example.com"}
    second = {"X-Forwarded-Email": "SYNTHETIC.second@example.com"}
    client_b = TestClient(client_a.app)
    assert upload(client_a, headers=first).status_code == 200
    assert upload(client_b, headers=second).status_code == 200

    results = {}
    thread = threading.Thread(target=lambda: results.update(first=_email(client_a, headers=first)))
    thread.start()
    try:
        assert entered.wait(10), "the first launch never reached the runner"
        busy = _email(client_b, headers=second)
        assert busy.status_code == 429
        assert busy.json() == {"detail": MSG_OUTLOOK_BUSY}
    finally:
        release.set()
        thread.join(10)
    assert not thread.is_alive()
    assert results["first"].status_code == 200
    assert len(runner.calls) == 1
    runner.on_run = None
    assert _email(client_b, headers=second).status_code == 200


def test_default_app_uses_the_process_wide_lock_and_real_runner():
    app = create_app(settings=make_settings(), services=FakeServices(), frontend_dist=MISSING_DIST)
    assert app.state.outlook.lock is outlook_module._LAUNCH_LOCK
    assert app.state.outlook.runner is run_powershell


# --------------------------------------------------------------------------- #
# Sign-in and logging
# --------------------------------------------------------------------------- #
def test_email_needs_sign_in():
    client, services, runner = _ready()
    assert client.post("/api/auth/logout").status_code == 204
    response = _email(client)
    assert response.status_code == 401
    assert response.json() == {"detail": MSG_NOT_SIGNED_IN}
    assert runner.calls == []


def test_recipient_addresses_are_never_logged(caplog):
    caplog.set_level(logging.DEBUG)
    runner = FakeRunner()
    client, _, _ = _ready(runner=runner)
    assert _email(client).status_code == 200
    runner.returncode, runner.stderr = 1, "SYNTHETIC cannot resolve SYNTHETIC.one@example.com"
    assert _email(client).status_code == 502
    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "(2 recipient(s))" in text
    for address in RECIPIENTS:
        assert address.lower() not in text.lower()


# --------------------------------------------------------------------------- #
# The "features" flag on /api/auth/me and /api/auth/login
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "platform,settings,expected",
    [
        ("win32", make_settings(), True),
        ("win32", make_settings(host="localhost"), True),
        ("win32", make_settings(outlook_email="off"), False),
        ("win32", make_settings(host="0.0.0.0"), False),
        ("win32", make_settings(host="0.0.0.0", outlook_email="on"), True),
        ("linux", make_settings(outlook_email="on"), False),
        ("darwin", make_settings(), False),
    ],
)
def test_features_flag_on_login_and_me(platform, settings, expected):
    client, _, _ = _client(settings, platform=platform)
    response = login(client)
    assert response.status_code == 200
    assert response.json() == {"user": {"name": "admin"}, "auth_mode": "local", "features": {"outlook_email": expected}}
    me = client.get("/api/auth/me")
    assert me.json() == {"user": {"name": "admin"}, "auth_mode": "local", "features": {"outlook_email": expected}}


@pytest.mark.parametrize(
    "platform,outlook_email,expected",
    [("win32", "auto", False), ("win32", "on", True), ("win32", "off", False), ("linux", "on", False)],
)
def test_features_flag_in_databricks_mode(platform, outlook_email, expected):
    client, _, _ = _client(make_settings(auth_mode="databricks", host="0.0.0.0", outlook_email=outlook_email), platform=platform)
    response = client.get("/api/auth/me", headers=WHO)
    assert response.status_code == 200
    assert response.json() == {
        "user": {"name": WHO["X-Forwarded-Email"]},
        "auth_mode": "databricks",
        "features": {"outlook_email": expected},
    }


# --------------------------------------------------------------------------- #
# OUTLOOK_EMAIL setting
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value", ["yes", "true", "SYNTHETIC", "auto "])
def test_invalid_outlook_email_setting_fails_at_startup(value):
    with pytest.raises(ValueError, match="OUTLOOK_EMAIL"):
        create_app(settings=make_settings(outlook_email=value), services=FakeServices(), frontend_dist=MISSING_DIST)


@pytest.mark.parametrize(
    "raw,expected", [(None, "auto"), ("", "auto"), (" On ", "on"), ("OFF", "off"), ("auto", "auto")]
)
def test_outlook_email_setting_from_environment(monkeypatch, raw, expected):
    from backend import settings as settings_module

    if raw is None:
        monkeypatch.delenv("OUTLOOK_EMAIL", raising=False)
    else:
        monkeypatch.setenv("OUTLOOK_EMAIL", raw)
    settings_module.get_settings.cache_clear()
    try:
        assert settings_module.get_settings().outlook_email == expected
    finally:
        settings_module.get_settings.cache_clear()


def test_forcing_outlook_email_on_for_a_shared_server_is_logged(caplog):
    caplog.set_level(logging.WARNING, logger="fmea")
    create_app(settings=make_settings(host="0.0.0.0", outlook_email="on"), services=FakeServices(), frontend_dist=MISSING_DIST)
    assert "OUTLOOK_EMAIL=on" in caplog.text
    caplog.clear()
    create_app(settings=make_settings(outlook_email="on"), services=FakeServices(), frontend_dist=MISSING_DIST)
    assert "OUTLOOK_EMAIL=on" not in caplog.text
