"""Ask Windows PowerShell's parser whether the "Email the PDF" script is valid.

The script (backend.mail.outlook.POWERSHELL_SCRIPT) is only parsed, never run:
Outlook is not started and nothing is sent. A deliberately broken copy is
parsed too, to show the check really rejects a bad script.

The test suite never starts PowerShell, so this check lives here instead.
Run it on Windows from the project root:

    python tools/check_outlook_script.py

Exit code 0 means the script parses; 1 means it does not (the parser's
messages are printed).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.mail.outlook import CREATE_NO_WINDOW, POWERSHELL_SCRIPT, powershell_path  # noqa: E402

# Parse $env:FMEA_PARSE_SCRIPT and report any syntax errors; nothing is executed.
PARSE_ONLY = (
    "$tokens = $null; $errors = $null; "
    "$ast = [System.Management.Automation.Language.Parser]::ParseInput("
    "$env:FMEA_PARSE_SCRIPT, [ref]$tokens, [ref]$errors); "
    "if ($errors.Count -gt 0) { foreach ($e in $errors) { [Console]::Error.WriteLine($e.Message) }; exit 1 }; "
    "exit 0"
)


def parse(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [powershell_path(), "-NoProfile", "-NonInteractive", "-Command", PARSE_ONLY],
        env=dict(os.environ, FMEA_PARSE_SCRIPT=script),
        capture_output=True,
        text=True,
        timeout=120,
        creationflags=CREATE_NO_WINDOW,
    )


def main() -> int:
    if sys.platform != "win32":
        print("This check needs Windows PowerShell; run it on Windows.")
        return 1
    result = parse(POWERSHELL_SCRIPT)
    if result.returncode != 0:
        print("The Outlook script does not parse:\n" + result.stderr.strip())
        return 1
    broken = parse(POWERSHELL_SCRIPT.replace("} catch {", "} catch {{", 1))
    if broken.returncode != 1 or "Missing closing" not in broken.stderr:
        print("The check did not reject a broken copy of the script, so its result cannot be trusted.")
        return 1
    print("OK: PowerShell's parser accepts the Outlook script (and rejects a broken copy).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
