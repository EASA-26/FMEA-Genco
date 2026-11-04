"""Print an ADMIN_PASSWORD_HASH line for a new sign-in password.

Usage (from the project root):
    python tools/hash_password.py              # asks for the password (recommended)
    python tools/hash_password.py <password>   # password on the command line

Copy the printed line into .env (locally) or into a Databricks secret.
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

# Allow running as a plain script from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.auth.passwords import hash_password  # noqa: E402


def _ask_for_password() -> str | None:
    first = getpass.getpass("New password: ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        print("The two passwords do not match. Nothing was created.", file=sys.stderr)
        return None
    return first


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        print("Usage: python tools/hash_password.py [password]", file=sys.stderr)
        return 2
    if argv:
        password = argv[0]
        print(
            "Note: a password typed on the command line may be kept in your shell history.",
            file=sys.stderr,
        )
    else:
        try:
            password = _ask_for_password()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.", file=sys.stderr)
            return 1
        if password is None:
            return 1
    if not password:
        print("The password cannot be empty.", file=sys.stderr)
        return 1
    print(f"ADMIN_PASSWORD_HASH={hash_password(password)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
