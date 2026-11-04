"""backend.mail.outlook: availability, recipient parsing, email content, the fixed
PowerShell script and the Outlook launch.

PowerShell and Outlook are never started: the launch uses `FakeRunner`, and the
real runner is checked with ``subprocess.run`` replaced. To have PowerShell's
own parser check the script on Windows (it is parsed, never run), use
``python tools/check_outlook_script.py``. All data is SYNTHETIC.
"""
from __future__ import annotations

import itertools
import logging
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import pytest

from backend.mail import outlook
from backend.mail.outlook import (
    CREATE_NO_WINDOW,
    ENV_ATTACHMENT,
    ENV_INTRO_HTML,
    ENV_SUBJECT,
    ENV_TO,
    FALLBACK_ATTACHMENT_NAME,
    LAUNCH_TIMEOUT_SECONDS,
    MAX_ATTACHMENT_NAME_LENGTH,
    MAX_RECIPIENTS,
    MAX_RECIPIENTS_TEXT,
    MSG_RECIPIENTS_TOO_LONG,
    MSG_TOO_MANY_RECIPIENTS,
    POWERSHELL_SCRIPT,
    OutlookBusy,
    OutlookFailed,
    OutlookMailer,
    RecipientError,
    RunResult,
    email_intro_html,
    email_subject,
    invalid_address_message,
    is_valid_address,
    outlook_email_available,
    parse_recipients,
    powershell_command,
    powershell_path,
    run_powershell,
    safe_attachment_name,
)
from backend.tests.test_api_support import FakeRunner, make_outlook, make_settings

SYNTHETIC_PDF_BYTES = b"%PDF-1.4\n% SYNTHETIC mail test PDF\n"
SYNTHETIC_STATION = "SYNTHETIC Station S9"
SYNTHETIC_DATE = "15 January 2026"
SYNTHETIC_RECIPIENTS = ["SYNTHETIC.one@example.com", "synthetic.two@example.org"]
SYNTHETIC_ATTACHMENT = "FMEA_Report_SYNTHETIC_Station_S9_2026-01-15.pdf"


# --------------------------------------------------------------------------- #
# Availability
# --------------------------------------------------------------------------- #
PLATFORMS = ["win32", "linux", "darwin", "cygwin", "SYNTHETIC-os"]
AUTH_MODES = ["local", "databricks"]
HOSTS = ["127.0.0.1", "localhost", "::1", "0.0.0.0", "192.0.2.10", "SYNTHETIC-host.example"]
SETTINGS = ["auto", "on", "off"]
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


@pytest.mark.parametrize(
    "platform,auth_mode,host,setting", list(itertools.product(PLATFORMS, AUTH_MODES, HOSTS, SETTINGS))
)
def test_availability_for_every_combination(platform, auth_mode, host, setting):
    settings = make_settings(auth_mode=auth_mode, host=host, outlook_email=setting)
    expected = (
        platform == "win32"
        and setting != "off"
        and (setting == "on" or (auth_mode == "local" and host in LOOPBACK))
    )
    assert outlook_email_available(settings, platform=platform) is expected
    assert make_outlook(platform=platform).available(settings) is expected


@pytest.mark.parametrize(
    "platform,auth_mode,host,setting,expected",
    [
        ("win32", "local", "127.0.0.1", "auto", True),     # the usual local install
        ("win32", "local", "0.0.0.0", "auto", False),      # reachable from other computers
        ("win32", "databricks", "0.0.0.0", "auto", False),
        ("win32", "databricks", "0.0.0.0", "on", True),    # explicitly forced on
        ("win32", "local", "127.0.0.1", "off", False),
        ("linux", "local", "127.0.0.1", "on", False),      # never outside Windows
        ("darwin", "local", "localhost", "auto", False),
    ],
)
def test_availability_key_cases(platform, auth_mode, host, setting, expected):
    settings = make_settings(auth_mode=auth_mode, host=host, outlook_email=setting)
    assert outlook_email_available(settings, platform=platform) is expected


@pytest.mark.parametrize(
    "setting,host,expected",
    [(" ON ", "0.0.0.0", True), ("Off", "127.0.0.1", False), ("AUTO", " LocalHost ", True), ("", "::1", True)],
)
def test_availability_ignores_case_and_spaces(setting, host, expected):
    settings = make_settings(host=host, outlook_email=setting)
    assert outlook_email_available(settings, platform="win32") is expected


def test_availability_defaults_to_this_platform():
    settings = make_settings()
    assert outlook_email_available(settings) is outlook_email_available(settings, platform=sys.platform)
    assert make_settings().outlook_email == "auto"


def test_mailer_defaults():
    mailer = OutlookMailer()
    assert mailer.runner is run_powershell
    assert mailer.platform == sys.platform
    assert mailer.timeout == LAUNCH_TIMEOUT_SECONDS == 120
    # One lock for the whole process, shared by every mailer (and so every session).
    assert mailer.lock is OutlookMailer().lock is outlook._LAUNCH_LOCK


# --------------------------------------------------------------------------- #
# Recipients
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text", ["", None, "   ", ";;, ,", "\n\r\n\t", " ; , \u00a0 "])
def test_empty_recipient_list_is_allowed(text):
    assert parse_recipients(text) == []


def test_every_separator_splits():
    text = (
        "a@example.com;b@example.org,c@example.net d@example.com\te@example.com\n"
        "f@example.com\r\ng@example.com\u00a0h@example.com ;, \n i@example.com"
    )
    assert parse_recipients(text) == [f"{c}@{d}" for c, d in zip(
        "abcdefghi",
        ["example.com", "example.org", "example.net"] + ["example.com"] * 6,
    )]


def test_recipients_are_trimmed_and_keep_their_spelling():
    assert parse_recipients("  SYNTHETIC.One@Example.COM  ;  b@example.org ") == [
        "SYNTHETIC.One@Example.COM",
        "b@example.org",
    ]


def test_duplicates_ignore_case_and_keep_the_first_spelling():
    text = "SYNTHETIC.A@Example.com; synthetic.a@example.com, b@example.org\nSYNTHETIC.A@EXAMPLE.COM"
    assert parse_recipients(text) == ["SYNTHETIC.A@Example.com", "b@example.org"]


def _addresses(count: int) -> list[str]:
    return [f"synthetic{n}@example.com" for n in range(count)]


def test_at_most_twenty_recipients():
    assert MAX_RECIPIENTS == 20
    assert parse_recipients("; ".join(_addresses(20))) == _addresses(20)
    with pytest.raises(RecipientError) as raised:
        parse_recipients("; ".join(_addresses(21)))
    assert raised.value.message == MSG_TOO_MANY_RECIPIENTS


def test_limit_counts_addresses_after_removing_duplicates():
    text = "; ".join(_addresses(20) + [a.upper() for a in _addresses(5)])
    assert parse_recipients(text) == _addresses(20)


def test_recipient_text_length_limit():
    assert MAX_RECIPIENTS_TEXT == 2000
    address = "synthetic@example.com"
    exactly = address + " " * (MAX_RECIPIENTS_TEXT - len(address))
    assert parse_recipients(exactly) == [address]
    for too_long in (exactly + " ", " " * (MAX_RECIPIENTS_TEXT + 1)):
        with pytest.raises(RecipientError) as raised:
            parse_recipients(too_long)
        assert raised.value.message == MSG_RECIPIENTS_TOO_LONG


@pytest.mark.parametrize(
    "address",
    [
        "a@b.c",
        "first.last+tag@sub.example.co",
        "SYNTHETIC_user-1@example-domain.com",
        "synthetic@exämple.com",
        "o'synthetic@example.com",         # an apostrophe is valid in the local part
        "x" * 64 + "@" + "d" * (254 - 64 - 1 - 4) + ".com",   # exactly 254 characters
    ],
)
def test_valid_addresses(address):
    assert is_valid_address(address)
    assert parse_recipients(address) == [address]


@pytest.mark.parametrize(
    "address",
    [
        "synthetic",                       # no @
        "synthetic@@example.com",          # two @
        "a@b@example.com",
        "@example.com",                    # empty local part
        "synthetic@",                      # empty domain
        "synthetic@localhost",             # domain without a dot
        "synthetic@.example.com",          # empty labels
        "synthetic@example..com",
        "synthetic@example.com.",
        '"synthetic"@example.com',         # double quotes
        "<synthetic@example.com>",         # angle brackets
        "synthetic@example.com>",
        "syn\x00thetic@example.com",       # control characters
        "syn\x7fthetic@example.com",
        "syn\x85thetic@example.com",
        "\x1csynthetic@example.com",       # control characters at the edges are not trimmed away
        "synthetic@example.com\x85",
        "syn\u200bthetic@example.com",     # zero-width space (format character)
        "syn\u202ethetic@example.com",     # right-to-left override
        "x" * 64 + "@" + "d" * (255 - 64 - 1 - 4) + ".com",   # 255 characters
    ],
)
def test_invalid_addresses_are_refused_by_name(address):
    assert not is_valid_address(address)
    with pytest.raises(RecipientError) as raised:
        parse_recipients(f"ok@example.com; {address}; also.ok@example.org")
    message = raised.value.message
    assert message == invalid_address_message(address)
    assert "is not a valid email address" in message
    assert not any(ord(ch) < 32 or 0x7F <= ord(ch) <= 0x9F or ch in "\u200b\u202e" for ch in message)


def test_spaces_commas_and_semicolons_cannot_be_inside_an_address():
    for ch in " ,;\t\n\u00a0":
        assert not is_valid_address(f"syn{ch}thetic@example.com")


def test_error_message_names_the_first_bad_address():
    with pytest.raises(RecipientError) as raised:
        parse_recipients("good@example.com, SYNTHETIC-first-bad, SYNTHETIC-second-bad")
    assert raised.value.message == '"SYNTHETIC-first-bad" is not a valid email address. Check it and try again.'


def test_error_message_is_printable_and_short():
    assert invalid_address_message("syn\x00the\u200btic") == (
        '"syn?the?tic" is not a valid email address. Check it and try again.'
    )
    long_message = invalid_address_message("SYNTHETIC" * 50)
    assert len(long_message) < 160 and '..." is not a valid' in long_message


def test_bad_address_is_reported_before_too_many():
    with pytest.raises(RecipientError) as raised:
        parse_recipients("; ".join(_addresses(25) + ["SYNTHETIC-bad"]))
    assert "SYNTHETIC-bad" in raised.value.message


def test_display_name_form_is_refused():
    with pytest.raises(RecipientError) as raised:
        parse_recipients("SYNTHETIC Person <synthetic.person@example.com>")
    assert '"SYNTHETIC"' in raised.value.message


# --------------------------------------------------------------------------- #
# Subject and introduction
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "station,date_text,expected",
    [
        (SYNTHETIC_STATION, SYNTHETIC_DATE, "FMEA Report - SYNTHETIC Station S9 - 15 January 2026"),
        ("", SYNTHETIC_DATE, "FMEA Report - 15 January 2026"),
        (SYNTHETIC_STATION, "", "FMEA Report - SYNTHETIC Station S9"),
        ("", "", "FMEA Report"),
        (None, None, "FMEA Report"),
        ("   ", "\t\n", "FMEA Report"),
        ("  SYNTHETIC\r\nStation\tS9  ", " 15  January\x002026 ", "FMEA Report - SYNTHETIC Station S9 - 15 January 2026"),
    ],
)
def test_email_subject(station, date_text, expected):
    subject = email_subject(station, date_text)
    assert subject == expected
    assert " -  " not in subject and not subject.endswith("-")


@pytest.mark.parametrize(
    "station,date_text,sentence",
    [
        (
            SYNTHETIC_STATION,
            SYNTHETIC_DATE,
            "Please find attached the Failure Mode Effect Analysis (FMEA) report for "
            "<b>SYNTHETIC Station S9</b> (Date of Analysis: 15 January 2026).",
        ),
        (
            "",
            SYNTHETIC_DATE,
            "Please find attached the Failure Mode Effect Analysis (FMEA) report (Date of Analysis: 15 January 2026).",
        ),
        (
            SYNTHETIC_STATION,
            " ",
            "Please find attached the Failure Mode Effect Analysis (FMEA) report for <b>SYNTHETIC Station S9</b>.",
        ),
        (None, None, "Please find attached the Failure Mode Effect Analysis (FMEA) report."),
    ],
)
def test_email_intro(station, date_text, sentence):
    assert email_intro_html(station, date_text) == f"Hello,<br><br>{sentence}<br><br>"


def test_email_intro_escapes_html():
    intro = email_intro_html("<script>alert('SYNTHETIC')</script> & \"S9\"", "<i>15 January 2026</i>")
    assert "<script" not in intro and "<i>" not in intro
    assert "&lt;script&gt;alert(&#x27;SYNTHETIC&#x27;)&lt;/script&gt; &amp; &quot;S9&quot;" in intro
    assert "(Date of Analysis: &lt;i&gt;15 January 2026&lt;/i&gt;)" in intro
    # The only tags are the ones the app writes itself.
    assert re.findall(r"<[^>]*>", intro) == ["<br>", "<br>", "<b>", "</b>", "<br>", "<br>"]


def test_email_intro_is_one_line():
    intro = email_intro_html("SYNTHETIC\nStation\r\nS9", "15\tJanuary 2026")
    assert "\n" not in intro and "\r" not in intro and "\t" not in intro
    assert "<b>SYNTHETIC Station S9</b> (Date of Analysis: 15 January 2026)" in intro


# --------------------------------------------------------------------------- #
# Attachment file name
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "name,expected",
    [
        ("FMEA_Report_SYNTHETIC_Station_2026-01-15.pdf", "FMEA_Report_SYNTHETIC_Station_2026-01-15.pdf"),
        ('FMEA<>:"/\\|?*.pdf', "FMEA_________.pdf"),
        ("SYNTHETIC\r\nname\x00.pdf", "SYNTHETIC__name_.pdf"),
        ("SYNTHETIC\u202ename.pdf", "SYNTHETIC_name.pdf"),
        ("..\\..\\SYNTHETIC.pdf", "_.._SYNTHETIC.pdf"),
        ("FMEA_Report_SYNTHETIC", "FMEA_Report_SYNTHETIC.pdf"),
        ("FMEA_Report_SYNTHETIC.PDF", "FMEA_Report_SYNTHETIC.pdf"),
        ("SYNTHETIC name. . .pdf", "SYNTHETIC name.pdf"),
        ("  SYNTHETIC   spaced  name .pdf", "SYNTHETIC spaced name.pdf"),
        ("FMEA_Report_SYNTHETIC_发电站.pdf", "FMEA_Report_SYNTHETIC_发电站.pdf"),
        ("CON.pdf", "_CON.pdf"),
        ("nul", "_nul.pdf"),
        ("COM1.SYNTHETIC.pdf", "_COM1.SYNTHETIC.pdf"),
        ("lpt9 .pdf", "_lpt9.pdf"),
        ("CONSOLE.pdf", "CONSOLE.pdf"),
        ("", FALLBACK_ATTACHMENT_NAME),
        (None, FALLBACK_ATTACHMENT_NAME),
        ("   ", FALLBACK_ATTACHMENT_NAME),
        (".pdf", FALLBACK_ATTACHMENT_NAME),
        ("...", FALLBACK_ATTACHMENT_NAME),
    ],
)
def test_safe_attachment_name(name, expected):
    safe = safe_attachment_name(name)
    assert safe == expected
    assert safe_attachment_name(safe) == safe   # applying it again changes nothing
    assert Path(safe).name == safe and "/" not in safe and "\\" not in safe


def test_safe_attachment_name_length():
    safe = safe_attachment_name("S" * 300 + ".pdf")
    assert len(safe) == MAX_ATTACHMENT_NAME_LENGTH and safe.endswith("S.pdf")
    # A cut that lands on spaces or dots does not leave them before ".pdf".
    safe = safe_attachment_name("S" * 140 + " ." * 20 + "X.pdf")
    assert safe == "S" * 140 + ".pdf"


# --------------------------------------------------------------------------- #
# The fixed PowerShell script and command line
# --------------------------------------------------------------------------- #
def test_script_reads_only_the_four_environment_variables():
    assert set(re.findall(r"\$env:(\w+)", POWERSHELL_SCRIPT)) == {
        ENV_TO, ENV_SUBJECT, ENV_INTRO_HTML, ENV_ATTACHMENT,
    }


def test_script_opens_a_draft_and_never_sends():
    script = POWERSHELL_SCRIPT
    for expected in (
        "$ErrorActionPreference = 'Stop'",
        "New-Object -ComObject Outlook.Application",
        "$outlook.CreateItem(0)",
        "$mail.To = $to",
        "$mail.Subject = $subject",
        "$mail.Attachments.Add($attachment)",
        "$mail.Display($false)",
        "$mail.HTMLBody = $body",
        "$mail.GetInspector.Activate()",
        "exit 0",
        "exit 1",
    ):
        assert expected in script, expected
    assert ".Send(" not in script and ".Send" + "\n" not in script
    # Display comes before the body is changed, so Outlook's default signature is
    # already in HTMLBody when the introduction is put above it.
    assert script.index("Display($false)") < script.index("[string]$mail.HTMLBody") < script.index("$mail.HTMLBody = $body")
    assert re.search(r"catch \{\s*\[Console\]::Error\.WriteLine\(\$_\.Exception\.Message\)\s*exit 1\s*\}", script)
    # Only bringing the window to the front may fail quietly: the email is open by then.
    assert script.count("catch { }") == 1
    assert "try { $mail.GetInspector.Activate() } catch { }" in script


def test_script_text_survives_the_windows_command_line():
    # No double quotes: Windows command-line quoting would have to escape them.
    assert '"' not in POWERSHELL_SCRIPT
    assert "\x00" not in POWERSHELL_SCRIPT and "`" not in POWERSHELL_SCRIPT
    assert subprocess.list2cmdline(["x", POWERSHELL_SCRIPT]) == "x " + '"' + POWERSHELL_SCRIPT + '"'


def _insert_like_the_script(body: str, intro: str) -> str:
    """The script's insertion step, replayed with the script's own pattern."""
    pattern = re.search(r"\[regex\]::Match\(\$body, '([^']+)', \$options\)", POWERSHELL_SCRIPT).group(1)
    match = re.search(pattern, body, re.IGNORECASE)
    return body[: match.end()] + intro + body[match.end():] if match else intro + body


@pytest.mark.parametrize(
    "body,expected",
    [
        (
            "<html><head></head><body lang=EN-US link=blue><p>SYNTHETIC signature</p></body></html>",
            "<html><head></head><body lang=EN-US link=blue>INTRO<p>SYNTHETIC signature</p></body></html>",
        ),
        ("<HTML><BODY>SYNTHETIC</BODY></HTML>", "<HTML><BODY>INTRO" + "SYNTHETIC</BODY></HTML>"),
        ("<html><bodyx>SYNTHETIC</bodyx><body>", "<html><bodyx>SYNTHETIC</bodyx><body>INTRO"),
        ("SYNTHETIC plain text", "INTROSYNTHETIC plain text"),
        ("", "INTRO"),
    ],
)
def test_script_puts_the_intro_right_after_the_body_tag(body, expected):
    assert _insert_like_the_script(body, "INTRO") == expected


def test_powershell_command_line():
    command = powershell_command()
    assert command[1:] == [
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", POWERSHELL_SCRIPT,
    ]
    assert command[0] == powershell_path()


def test_powershell_path_is_absolute(monkeypatch):
    monkeypatch.setenv("SystemRoot", r"C:\SYNTHETIC-Windows")
    assert powershell_path() == str(Path(r"C:\SYNTHETIC-Windows") / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
    monkeypatch.delenv("SystemRoot")
    monkeypatch.setenv("windir", r"D:\SYNTHETIC-windir")
    assert powershell_path().startswith(str(Path(r"D:\SYNTHETIC-windir")))
    monkeypatch.delenv("windir")
    assert powershell_path().endswith("powershell.exe") and Path(powershell_path()).name == "powershell.exe"


@pytest.mark.parametrize("platform,flags", [("win32", CREATE_NO_WINDOW), ("linux", 0)])
def test_real_runner_starts_powershell_hidden_and_waits(monkeypatch, platform, flags):
    captured = {}

    def fake_run(args, **kwargs):
        captured.update(args=args, **kwargs)
        return subprocess.CompletedProcess(args, 3, stdout=None, stderr="SYNTHETIC error ✓".encode())

    monkeypatch.setattr(outlook.subprocess, "run", fake_run)
    monkeypatch.setattr(outlook.sys, "platform", platform)
    env = {"SYNTHETIC_VAR": "1"}
    result = run_powershell(("SYNTHETIC-powershell.exe", "-Command", "x"), env, 120)
    assert result == RunResult(3, "SYNTHETIC error ✓")
    assert captured["args"] == ["SYNTHETIC-powershell.exe", "-Command", "x"]
    assert captured["env"] is env
    assert captured["timeout"] == 120
    assert captured["creationflags"] == flags
    assert captured["stdin"] is subprocess.DEVNULL and captured["stdout"] is subprocess.DEVNULL
    assert captured["stderr"] is subprocess.PIPE and captured["check"] is False
    assert "shell" not in captured


def test_real_runner_passes_on_timeouts(monkeypatch):
    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])

    monkeypatch.setattr(outlook.subprocess, "run", fake_run)
    with pytest.raises(subprocess.TimeoutExpired):
        run_powershell(["SYNTHETIC"], {}, 1)
    monkeypatch.setattr(outlook.subprocess, "run", lambda args, **kw: subprocess.CompletedProcess(args, 0, None, None))
    assert run_powershell(["SYNTHETIC"], {}, 1) == RunResult(0, "")


# --------------------------------------------------------------------------- #
# Opening the draft (fake runner)
# --------------------------------------------------------------------------- #
def _open(mailer: OutlookMailer, **overrides) -> None:
    values = dict(
        recipients=SYNTHETIC_RECIPIENTS,
        subject=email_subject(SYNTHETIC_STATION, SYNTHETIC_DATE),
        intro_html=email_intro_html(SYNTHETIC_STATION, SYNTHETIC_DATE),
        pdf_bytes=SYNTHETIC_PDF_BYTES,
        attachment_name=SYNTHETIC_ATTACHMENT,
    )
    values.update(overrides)
    mailer.open_draft(**values)


def _assert_removed(call) -> None:
    folder = call.attachment.parent
    assert folder.name.startswith("fmea-mail-")
    assert not folder.exists(), f"temporary folder left behind: {folder}"


def test_open_draft_passes_values_only_through_the_environment(monkeypatch):
    monkeypatch.setenv("SYNTHETIC_INHERITED", "kept")
    runner = FakeRunner()
    mailer = make_outlook(runner, platform="win32")
    _open(mailer)

    [call] = runner.calls
    assert call.args == powershell_command()
    assert call.args[-1] is POWERSHELL_SCRIPT
    assert call.timeout == LAUNCH_TIMEOUT_SECONDS
    assert call.env[ENV_TO] == "SYNTHETIC.one@example.com; synthetic.two@example.org"
    assert call.env[ENV_SUBJECT] == "FMEA Report - SYNTHETIC Station S9 - 15 January 2026"
    assert call.env[ENV_INTRO_HTML] == email_intro_html(SYNTHETIC_STATION, SYNTHETIC_DATE)
    assert call.env[ENV_ATTACHMENT] == str(call.attachment)
    # The rest of the environment is inherited (PowerShell needs PATH, SystemRoot...).
    assert call.env["SYNTHETIC_INHERITED"] == "kept"

    # The PDF was in a fresh temporary folder while PowerShell ran...
    assert call.attachment.name == SYNTHETIC_ATTACHMENT
    assert call.attachment_bytes == SYNTHETIC_PDF_BYTES
    assert Path(tempfile.gettempdir()).resolve() in call.attachment.resolve().parents
    # ...and is gone now.
    _assert_removed(call)


def test_script_and_arguments_never_contain_user_values():
    runner = FakeRunner()
    mailer = make_outlook(runner, platform="win32")
    _open(mailer)
    _open(
        mailer,
        recipients=["SYNTHETIC.other@example.net"],
        subject="FMEA Report - SYNTHETIC'; Remove-Item C:\\ -Recurse; '",
        intro_html="$(Start-Process SYNTHETIC.exe)",
        attachment_name="SYNTHETIC $(evil) `backtick`.pdf",
    )
    first, second = runner.calls
    assert first.args == second.args == powershell_command()
    user_values = SYNTHETIC_RECIPIENTS + [
        "SYNTHETIC.other@example.net", "SYNTHETIC Station", "Remove-Item", "Start-Process", "evil", "fmea-mail-",
    ]
    for arg in first.args + second.args:
        for value in user_values:
            assert value not in arg, (value, arg)
    assert second.env[ENV_INTRO_HTML] == "$(Start-Process SYNTHETIC.exe)"


def test_empty_recipients_leave_to_empty():
    runner = FakeRunner()
    _open(make_outlook(runner, platform="win32"), recipients=[])
    assert runner.calls[0].env[ENV_TO] == ""


def test_nul_characters_never_reach_the_environment():
    runner = FakeRunner()
    _open(make_outlook(runner, platform="win32"), subject="SYNTHETIC\x00subject", intro_html="SYNTHETIC\x00intro")
    env = runner.calls[0].env
    assert env[ENV_SUBJECT] == "SYNTHETICsubject" and env[ENV_INTRO_HTML] == "SYNTHETICintro"


def test_attachment_name_is_made_safe_inside_the_launcher():
    runner = FakeRunner()
    _open(make_outlook(runner, platform="win32"), attachment_name="..\\SYNTHETIC/na:me")
    call = runner.calls[0]
    assert call.attachment.name == "_SYNTHETIC_na_me.pdf"
    assert call.attachment.parent.name.startswith("fmea-mail-")
    _assert_removed(call)


@pytest.mark.parametrize(
    "runner",
    [
        FakeRunner(returncode=1, stderr="SYNTHETIC Outlook error"),
        FakeRunner(returncode=-1),
        FakeRunner(error=subprocess.TimeoutExpired(["SYNTHETIC"], 120)),
        FakeRunner(error=FileNotFoundError("SYNTHETIC powershell.exe missing")),
        FakeRunner(error=PermissionError("SYNTHETIC blocked")),
    ],
    ids=["exit-1", "exit-negative", "timeout", "not-found", "blocked"],
)
def test_failures_raise_outlook_failed_and_clean_up(runner):
    mailer = make_outlook(runner, platform="win32")
    with pytest.raises(OutlookFailed):
        _open(mailer)
    _assert_removed(runner.calls[0])
    assert not mailer.lock.locked()
    # The next attempt is not blocked by the failed one.
    runner.error, runner.returncode = None, 0
    _open(mailer)
    assert len(runner.calls) == 2


def test_unexpected_runner_error_still_cleans_up():
    runner = FakeRunner(error=RuntimeError("SYNTHETIC unexpected"))
    mailer = make_outlook(runner, platform="win32")
    with pytest.raises(RuntimeError):
        _open(mailer)
    _assert_removed(runner.calls[0])
    assert not mailer.lock.locked()


def test_busy_while_the_lock_is_held():
    runner = FakeRunner()
    mailer = make_outlook(runner, platform="win32")
    assert mailer.lock.acquire(blocking=False)
    try:
        with pytest.raises(OutlookBusy):
            _open(mailer)
    finally:
        mailer.lock.release()
    assert runner.calls == []
    _open(mailer)
    assert len(runner.calls) == 1


def test_second_launch_while_the_first_runs_is_refused_without_waiting():
    entered, release = threading.Event(), threading.Event()

    def block():
        entered.set()
        assert release.wait(10)

    runner = FakeRunner(on_run=block)
    lock = threading.Lock()
    first, second = make_outlook(runner, platform="win32", lock=lock), make_outlook(FakeRunner(), platform="win32", lock=lock)
    errors: list[BaseException] = []

    def run_first():
        try:
            _open(first)
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)

    thread = threading.Thread(target=run_first)
    thread.start()
    try:
        assert entered.wait(10)
        with pytest.raises(OutlookBusy):
            _open(second)      # another mailer sharing the lock: refused at once
        with pytest.raises(OutlookBusy):
            _open(first)
    finally:
        release.set()
        thread.join(10)
    assert errors == [] and not thread.is_alive()
    assert len(runner.calls) == 1
    runner.on_run = None
    _open(first)
    assert len(runner.calls) == 2


def test_recipients_are_never_logged(caplog):
    caplog.set_level(logging.DEBUG)
    stderr = "SYNTHETIC: cannot resolve SYNTHETIC.one@example.com;synthetic.two@example.org (0x800)"
    for runner in (
        FakeRunner(),
        FakeRunner(returncode=1, stderr=stderr),
        FakeRunner(error=subprocess.TimeoutExpired(["SYNTHETIC"], 120)),
        FakeRunner(error=OSError("SYNTHETIC")),
    ):
        try:
            _open(make_outlook(runner, platform="win32"))
        except OutlookFailed:
            pass
    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "exit code 1" in text and "<address>" in text and "0x800" in text
    for address in SYNTHETIC_RECIPIENTS:
        assert address.lower() not in text.lower()


def test_folder_that_cannot_be_removed_is_logged_not_raised(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    real_rmtree = outlook.shutil.rmtree
    monkeypatch.setattr(outlook.shutil, "rmtree", lambda path, ignore_errors=False: None)
    monkeypatch.setattr(outlook.time, "sleep", lambda seconds: None)
    runner = FakeRunner()
    _open(make_outlook(runner, platform="win32"))
    folder = runner.calls[0].attachment.parent
    try:
        assert folder.exists()
        assert "Could not remove the temporary email folder" in caplog.text
    finally:
        real_rmtree(folder, ignore_errors=True)


def test_folder_removal_is_retried(monkeypatch):
    real_rmtree = outlook.shutil.rmtree
    attempts = []

    def flaky_rmtree(path, ignore_errors=False):
        attempts.append(path)
        if len(attempts) > 1:          # e.g. a virus scanner let go of the file
            real_rmtree(path, ignore_errors=ignore_errors)

    monkeypatch.setattr(outlook.shutil, "rmtree", flaky_rmtree)
    monkeypatch.setattr(outlook.time, "sleep", lambda seconds: None)
    runner = FakeRunner()
    _open(make_outlook(runner, platform="win32"))
    assert len(attempts) == 2
    _assert_removed(runner.calls[0])
