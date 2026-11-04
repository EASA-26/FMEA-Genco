"""Password hashing and the hash_password tool."""
from __future__ import annotations

import base64
import importlib.util
import re
import time
from pathlib import Path

import pytest

from backend.auth.passwords import hash_password, is_password_hash, verify_password
from backend.settings import DEFAULT_ADMIN_PASSWORD_HASH, PROJECT_ROOT


def _documented_dev_password() -> str:
    """The initial development password, read from its one documented place (settings.py),
    so it is never repeated in the code base."""
    note = (Path(PROJECT_ROOT) / "backend" / "settings.py").read_text(encoding="utf-8")
    match = re.search(r'initial development password \("([^"]+)"\)', note)
    assert match, "settings.py should document the initial development password"
    return match.group(1)


DEV = _documented_dev_password()


def test_default_hash_accepts_the_documented_development_password():
    assert verify_password(DEV, DEFAULT_ADMIN_PASSWORD_HASH) is True


@pytest.mark.parametrize(
    "wrong",
    [DEV[:-1] + ("x" if DEV[-1] != "x" else "y"), DEV.upper(), DEV + " ", " " + DEV, DEV[:-1], "", "admin"],
    ids=["last-char-changed", "upper-case", "trailing-space", "leading-space", "shorter", "empty", "admin"],
)
def test_default_hash_rejects_other_passwords(wrong):
    assert verify_password(wrong, DEFAULT_ADMIN_PASSWORD_HASH) is False


def test_hash_format_matches_contract():
    encoded = hash_password("SYNTHETIC-password")
    algorithm, n, r, p, salt, key = encoded.split("$")
    assert (algorithm, n, r, p) == ("scrypt", "16384", "8", "1")
    assert len(base64.b64decode(salt, validate=True)) == 16
    assert len(base64.b64decode(key, validate=True)) == 32
    assert verify_password("SYNTHETIC-password", encoded)
    assert not verify_password("SYNTHETIC-passwore", encoded)
    assert is_password_hash(encoded)


def test_each_hash_uses_a_new_salt():
    first, second = hash_password("same"), hash_password("same")
    assert first != second
    assert verify_password("same", first) and verify_password("same", second)


def test_unicode_passwords_round_trip():
    encoded = hash_password("kata-laluan-ß-密码")
    assert verify_password("kata-laluan-ß-密码", encoded)
    assert not verify_password("kata-laluan-ss-密码", encoded)


VALID = DEFAULT_ADMIN_PASSWORD_HASH
SALT, KEY = VALID.split("$")[4], VALID.split("$")[5]


@pytest.mark.parametrize(
    "encoded",
    [
        "",
        DEV,
        "scrypt$16384$8$1$onlyfive",
        f"bcrypt$16384$8$1${SALT}${KEY}",
        f"scrypt$abc$8$1${SALT}${KEY}",
        f"scrypt$16383$8$1${SALT}${KEY}",          # n not a power of two
        f"scrypt$1073741824$8$1${SALT}${KEY}",     # n far too large (would exhaust memory)
        f"scrypt$16384$0$1${SALT}${KEY}",
        f"scrypt$16384$8$1$not base64!${KEY}",
        f"scrypt$16384$8$1${SALT}$@@@",
        f"scrypt$16384$8$1$${KEY}",                # empty salt
        f"scrypt$16384$8$1${SALT}$QUJD",           # key too short
        VALID + "$extra",
    ],
    ids=[
        "empty", "plain-password", "too-few-parts", "other-algorithm", "n-not-number", "n-not-power-of-two",
        "n-too-large", "r-zero", "salt-not-base64", "key-not-base64", "salt-empty", "key-too-short", "extra-part",
    ],
)
def test_malformed_hashes_are_rejected_without_error(encoded):
    started = time.perf_counter()
    assert verify_password(DEV, encoded) is False
    assert is_password_hash(encoded) is False
    assert time.perf_counter() - started < 2


@pytest.mark.parametrize("bad_input", [None, 123, DEV.encode()], ids=["none", "int", "bytes"])
def test_non_string_inputs_are_rejected(bad_input):
    assert verify_password(bad_input, VALID) is False
    assert verify_password(DEV, bad_input) is False


def test_lone_surrogate_password_is_rejected_not_raised():
    assert verify_password("\ud800", VALID) is False


# --------------------------------------------------------------------------- #
# tools/hash_password.py
# --------------------------------------------------------------------------- #
def _load_tool():
    path = Path(PROJECT_ROOT) / "tools" / "hash_password.py"
    spec = importlib.util.spec_from_file_location("fmea_hash_password_tool", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _printed_hash(output: str) -> str:
    line = output.strip().splitlines()[-1]
    assert line.startswith("ADMIN_PASSWORD_HASH=")
    return line.split("=", 1)[1]


def test_tool_hashes_password_from_argv(capsys):
    tool = _load_tool()
    assert tool.main(["SYNTHETIC-secret"]) == 0
    captured = capsys.readouterr()
    assert verify_password("SYNTHETIC-secret", _printed_hash(captured.out))
    assert "history" in captured.err


def test_tool_prompts_twice(monkeypatch, capsys):
    tool = _load_tool()
    answers = iter(["SYNTHETIC-prompted", "SYNTHETIC-prompted"])
    monkeypatch.setattr(tool.getpass, "getpass", lambda prompt="": next(answers))
    assert tool.main([]) == 0
    assert verify_password("SYNTHETIC-prompted", _printed_hash(capsys.readouterr().out))


def test_tool_refuses_mismatched_or_empty_passwords(monkeypatch, capsys):
    tool = _load_tool()
    answers = iter(["one", "two"])
    monkeypatch.setattr(tool.getpass, "getpass", lambda prompt="": next(answers))
    assert tool.main([]) == 1
    assert tool.main([""]) == 1
    assert "ADMIN_PASSWORD_HASH=" not in capsys.readouterr().out
