"""Open a new classic-Outlook email with the report PDF attached (local Windows only).

The app never sends email itself. `OutlookMailer.open_draft` starts Windows
PowerShell, which asks the Outlook desktop app (COM automation) for a new
message, fills in To and Subject, attaches the PDF, shows the message and puts
a short introduction above the user's default signature. The user checks the
message and presses Send in Outlook.

Safety:

* The PowerShell script is fixed text (`POWERSHELL_SCRIPT`). The recipients,
  subject, introduction and attachment path reach it only through environment
  variables, so nothing typed by a user or read from a workbook can change
  what the script does.
* The PDF is written to a fresh temporary folder that is always removed
  afterwards (Outlook copies the file into the draft when it is attached).
* Only one Outlook launch runs at a time in this process (`OutlookBusy`).
* Recipient addresses are never written to the log, only their number.

The function that starts PowerShell (the "runner") is injectable, so tests
never launch PowerShell or Outlook.
"""
from __future__ import annotations

import html
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple

from backend.settings import Settings

logger = logging.getLogger("fmea.mail")

# --------------------------------------------------------------------------- #
# Availability (OUTLOOK_EMAIL setting)
# --------------------------------------------------------------------------- #
OUTLOOK_EMAIL_AUTO = "auto"
OUTLOOK_EMAIL_ON = "on"
OUTLOOK_EMAIL_OFF = "off"
OUTLOOK_EMAIL_MODES = (OUTLOOK_EMAIL_AUTO, OUTLOOK_EMAIL_ON, OUTLOOK_EMAIL_OFF)

# HOST values meaning "this computer only": the browser and Outlook are on the same PC.
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def outlook_email_available(settings: Settings, platform: str = sys.platform) -> bool:
    """True when "Email the PDF" can be offered.

    Only on Windows, never with ``OUTLOOK_EMAIL=off``; with ``on`` always,
    with ``auto`` (the default) only when the app runs on the user's own
    computer: ``AUTH_MODE=local`` and ``HOST`` is a loopback name.
    """
    if platform != "win32":
        return False
    mode = (settings.outlook_email or OUTLOOK_EMAIL_AUTO).strip().lower()
    if mode == OUTLOOK_EMAIL_OFF:
        return False
    if mode == OUTLOOK_EMAIL_ON:
        return True
    return settings.auth_mode == "local" and settings.host.strip().lower() in LOCAL_HOSTS


# --------------------------------------------------------------------------- #
# Recipients
# --------------------------------------------------------------------------- #
MAX_RECIPIENTS_TEXT = 2000
MAX_RECIPIENTS = 20
MAX_ADDRESS_LENGTH = 254

MSG_RECIPIENTS_TOO_LONG = (
    f"The list of email addresses is too long. Enter at most {MAX_RECIPIENTS} addresses."
)
MSG_TOO_MANY_RECIPIENTS = f"Enter at most {MAX_RECIPIENTS} email addresses."

# Separators: semicolon, comma and whitespace. The whitespace set is exactly
# JavaScript's \s, so the browser and the server split a list the same way.
_SEPARATORS = re.compile(
    "[;,\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+"
)
# Never allowed in an address (spaces and control characters are checked separately).
# An apostrophe is allowed: it is valid in the local part (o'name@...) and the
# values reach PowerShell only through environment variables.
_FORBIDDEN_IN_ADDRESS = frozenset('"<>,;')
_SHOWN_ADDRESS_LENGTH = 80


class RecipientError(ValueError):
    """The recipient list cannot be used; ``message`` is shown to the user."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _is_control_or_space(ch: str) -> bool:
    # Categories C* (control, format such as zero-width or bidi marks,
    # surrogate, private use, unassigned) and Z* (spaces, line separators).
    return ch.isspace() or unicodedata.category(ch)[0] in ("C", "Z")


def is_valid_address(address: str) -> bool:
    """A plain ``local@domain.tld`` address.

    Exactly one ``@``, a non-empty local part, a domain with at least one dot
    and no empty labels, at most `MAX_ADDRESS_LENGTH` characters, and no
    spaces, control characters, double quotes, angle brackets, commas or
    semicolons.
    """
    if not address or len(address) > MAX_ADDRESS_LENGTH or address.count("@") != 1:
        return False
    if any(ch in _FORBIDDEN_IN_ADDRESS or _is_control_or_space(ch) for ch in address):
        return False
    local, domain = address.split("@")
    labels = domain.split(".")
    return bool(local) and len(labels) >= 2 and all(labels)


def _shown(address: str) -> str:
    """The address as quoted back in an error message: printable and not too long."""
    text = "".join("?" if _is_control_or_space(ch) else ch for ch in address)
    if len(text) > _SHOWN_ADDRESS_LENGTH:
        text = text[: _SHOWN_ADDRESS_LENGTH - 3] + "..."
    return text


def invalid_address_message(address: str) -> str:
    return f'"{_shown(address)}" is not a valid email address. Check it and try again.'


def parse_recipients(text: str | None) -> list[str]:
    """Split, check and de-duplicate a typed recipient list.

    Split on ``;``, ``,`` and whitespace (including new lines); empty entries
    are dropped; duplicates (ignoring case) keep their first spelling; at most
    `MAX_RECIPIENTS`. An empty list is fine: the user then picks recipients in
    Outlook. Raises `RecipientError` naming the first bad address.
    """
    text = text or ""
    if len(text) > MAX_RECIPIENTS_TEXT:
        raise RecipientError(MSG_RECIPIENTS_TOO_LONG)
    recipients: list[str] = []
    seen: set[str] = set()
    for address in _SEPARATORS.split(text):
        # No further strip(): the split already removed every separator, and
        # Python's strip() would also drop characters such as - and 
        # that the browser's check (JavaScript trim) keeps and refuses.
        if not address:
            continue
        if not is_valid_address(address):
            raise RecipientError(invalid_address_message(address))
        key = address.lower()
        if key in seen:
            continue
        seen.add(key)
        recipients.append(address)
    if len(recipients) > MAX_RECIPIENTS:
        raise RecipientError(MSG_TOO_MANY_RECIPIENTS)
    return recipients


# --------------------------------------------------------------------------- #
# Email content
# --------------------------------------------------------------------------- #
SUBJECT_PREFIX = "FMEA Report"


def _one_line(text: str | None) -> str:
    """Workbook text made safe for one line: control characters and line breaks
    become spaces, runs of spaces collapse."""
    cleaned = "".join(" " if _is_control_or_space(ch) else ch for ch in text or "")
    return " ".join(cleaned.split())


def email_subject(station: str | None, analysis_date_text: str | None) -> str:
    """``FMEA Report - <station> - <date>``; missing parts are left out."""
    parts = [SUBJECT_PREFIX] + [part for part in (_one_line(station), _one_line(analysis_date_text)) if part]
    return " - ".join(parts)


def email_intro_html(station: str | None, analysis_date_text: str | None) -> str:
    """The HTML introduction placed above the user's Outlook signature."""
    station = _one_line(station)
    date_text = _one_line(analysis_date_text)
    sentence = "Please find attached the Failure Mode Effect Analysis (FMEA) report"
    if station:
        sentence += f" for <b>{html.escape(station, quote=True)}</b>"
    if date_text:
        sentence += f" (Date of Analysis: {html.escape(date_text, quote=True)})"
    return f"Hello,<br><br>{sentence}.<br><br>"


FALLBACK_ATTACHMENT_NAME = "FMEA_Report.pdf"
MAX_ATTACHMENT_NAME_LENGTH = 150
_UNSAFE_FILENAME_CHARS = frozenset('<>:"/\\|?*')
_WINDOWS_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(10)} | {f"LPT{i}" for i in range(10)}
)


def safe_attachment_name(name: str | None) -> str:
    """The report's PDF file name, usable as a Windows file name.

    Characters Windows does not allow, control and format characters become
    ``_``; spaces collapse; leading/trailing spaces and dots go; device names
    (CON, NUL, COM1...) get a ``_`` prefix; the name ends in ``.pdf`` and is at
    most `MAX_ATTACHMENT_NAME_LENGTH` characters. Applying it twice changes
    nothing.
    """
    cleaned = "".join(
        "_" if ch in _UNSAFE_FILENAME_CHARS or unicodedata.category(ch)[0] == "C" else ch
        for ch in name or ""
    )
    cleaned = " ".join(cleaned.split())
    stem = cleaned[:-4] if cleaned.lower().endswith(".pdf") else cleaned
    stem = stem.strip(" .")
    if not stem:
        return FALLBACK_ATTACHMENT_NAME
    if stem.split(".", 1)[0].strip().upper() in _WINDOWS_DEVICE_NAMES:
        stem = "_" + stem
    stem = stem[: MAX_ATTACHMENT_NAME_LENGTH - len(".pdf")].rstrip(" .")
    return stem + ".pdf"


# --------------------------------------------------------------------------- #
# PowerShell
# --------------------------------------------------------------------------- #
ENV_TO = "FMEA_MAIL_TO"
ENV_SUBJECT = "FMEA_MAIL_SUBJECT"
ENV_INTRO_HTML = "FMEA_MAIL_INTRO_HTML"
ENV_ATTACHMENT = "FMEA_MAIL_ATTACHMENT"

# Fixed script: every value comes from the environment variables above. It
# contains no double quotes, so it passes through the Windows command line
# unchanged. Display (never Send): the user sends the email from Outlook.
# Display comes first so Outlook adds the default signature; the introduction
# is then put right after the <body> tag, above it. Any failure exits with 1
# (bringing the window to the front is best-effort: the email is open anyway).
POWERSHELL_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
try {
    $to = [string]$env:FMEA_MAIL_TO
    $subject = [string]$env:FMEA_MAIL_SUBJECT
    $intro = [string]$env:FMEA_MAIL_INTRO_HTML
    $attachment = [string]$env:FMEA_MAIL_ATTACHMENT
    if (-not $attachment -or -not (Test-Path -LiteralPath $attachment -PathType Leaf)) {
        throw 'The PDF to attach was not found.'
    }
    $outlook = New-Object -ComObject Outlook.Application
    $mail = $outlook.CreateItem(0)
    $mail.BodyFormat = 2
    if ($to) { $mail.To = $to }
    $mail.Subject = $subject
    $null = $mail.Attachments.Add($attachment)
    $mail.Display($false)
    $body = [string]$mail.HTMLBody
    $options = [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    $match = [regex]::Match($body, '<body(\s[^>]*)?>', $options)
    if ($match.Success) {
        $body = $body.Insert($match.Index + $match.Length, $intro)
    } else {
        $body = $intro + $body
    }
    $mail.HTMLBody = $body
    # Bring the new email to the front; the email is open either way.
    try { $mail.GetInspector.Activate() } catch { }
    exit 0
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
""".strip()

LAUNCH_TIMEOUT_SECONDS = 120.0
# Keeps the PowerShell console window from flashing up.
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
_MAX_LOGGED_ERROR = 300
_EMAIL_LIKE = re.compile(r"[^\s;,<>\"']+@[^\s;,<>\"']+")


class RunResult(NamedTuple):
    returncode: int
    stderr: str = ""


# runner(args, env, timeout) -> RunResult; raises subprocess.TimeoutExpired or OSError.
Runner = Callable[[Sequence[str], dict[str, str], float], RunResult]


def powershell_path() -> str:
    """Full path of Windows PowerShell.

    A full path, never a bare ``powershell.exe``: Windows would look in the
    current folder first, where a file of that name could be planted.
    """
    root = os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"
    return str(Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")


def powershell_command() -> list[str]:
    return [
        powershell_path(),
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        POWERSHELL_SCRIPT,
    ]


def run_powershell(args: Sequence[str], env: dict[str, str], timeout: float) -> RunResult:
    """The real runner: start PowerShell without a window and wait for it."""
    completed = subprocess.run(
        list(args),
        env=env,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        check=False,
    )
    stderr = completed.stderr.decode("utf-8", errors="replace") if completed.stderr else ""
    return RunResult(completed.returncode, stderr)


# --------------------------------------------------------------------------- #
# Opening the draft
# --------------------------------------------------------------------------- #
class OutlookError(Exception):
    """Base class for Outlook launch failures."""


class OutlookBusy(OutlookError):
    """Another Outlook launch is still running in this process."""


class OutlookFailed(OutlookError):
    """PowerShell or Outlook failed, could not be started or took too long."""


# One launch at a time for the whole process (all sessions).
_LAUNCH_LOCK = threading.Lock()


def _log_safe(text: str) -> str:
    """PowerShell's error text for the log, with anything address-like removed."""
    return _EMAIL_LIKE.sub("<address>", text or "").strip()[:_MAX_LOGGED_ERROR]


def _remove_folder(folder: str) -> None:
    for attempt in range(3):
        shutil.rmtree(folder, ignore_errors=True)
        if not os.path.exists(folder):
            return
        time.sleep(0.2 * (attempt + 1))  # a virus scanner may still hold the file
    logger.warning("Could not remove the temporary email folder %s.", folder)


class OutlookMailer:
    """Opens Outlook drafts. One instance lives on ``app.state.outlook``.

    ``runner`` and ``platform`` are for tests (a fake runner never starts
    PowerShell; ``platform`` decides availability). ``lock`` defaults to the
    process-wide launch lock.
    """

    def __init__(
        self,
        runner: Runner | None = None,
        platform: str = sys.platform,
        timeout: float = LAUNCH_TIMEOUT_SECONDS,
        lock: threading.Lock | None = None,
    ) -> None:
        self.runner: Runner = runner if runner is not None else run_powershell
        self.platform = platform
        self.timeout = timeout
        self.lock = lock if lock is not None else _LAUNCH_LOCK

    def available(self, settings: Settings) -> bool:
        return outlook_email_available(settings, platform=self.platform)

    def open_draft(
        self,
        *,
        recipients: Sequence[str],
        subject: str,
        intro_html: str,
        pdf_bytes: bytes,
        attachment_name: str,
    ) -> None:
        """Show a new Outlook email with the PDF attached. Blocking; run it in a thread.

        Raises `OutlookBusy` when another launch is running and `OutlookFailed`
        when PowerShell or Outlook fails or times out.
        """
        if not self.lock.acquire(blocking=False):
            raise OutlookBusy()
        try:
            self._launch(list(recipients), subject, intro_html, pdf_bytes, safe_attachment_name(attachment_name))
        finally:
            self.lock.release()

    def _launch(
        self, recipients: list[str], subject: str, intro_html: str, pdf_bytes: bytes, attachment_name: str
    ) -> None:
        folder = tempfile.mkdtemp(prefix="fmea-mail-")
        try:
            attachment = Path(folder) / attachment_name
            attachment.write_bytes(pdf_bytes)
            env = dict(os.environ)
            values = {
                ENV_TO: "; ".join(recipients),
                ENV_SUBJECT: subject,
                ENV_INTRO_HTML: intro_html,
                ENV_ATTACHMENT: str(attachment),
            }
            # Environment values cannot hold NUL characters.
            env.update({name: value.replace(chr(0), "") for name, value in values.items()})
            try:
                result = self.runner(powershell_command(), env, self.timeout)
            except subprocess.TimeoutExpired:
                logger.warning("Outlook did not open a new email within %d seconds.", int(self.timeout))
                raise OutlookFailed() from None
            except OSError as exc:
                logger.warning("PowerShell could not be started to open Outlook (%s).", type(exc).__name__)
                raise OutlookFailed() from None
            if result.returncode != 0:
                logger.warning(
                    "Outlook could not open a new email (exit code %s): %r",
                    result.returncode,
                    _log_safe(result.stderr),
                )
                raise OutlookFailed()
        finally:
            _remove_folder(folder)
