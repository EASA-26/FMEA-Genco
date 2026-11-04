"""Password hashing with scrypt (standard library only).

Encoded format: ``scrypt$<n>$<r>$<p>$<salt b64>$<derived key b64>``.
New hashes use n=16384, r=8, p=1, a 16-byte random salt and a 32-byte key.
Generate one for ADMIN_PASSWORD_HASH with ``python tools/hash_password.py``.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets

ALGORITHM = "scrypt"
SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
KEY_BYTES = 32

# Upper bounds accepted when verifying, so a mistyped or hostile hash setting
# cannot make every sign-in attempt consume gigabytes of memory.
_MAX_N = 1 << 17
_MAX_R = 16
_MAX_P = 4


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, dklen: int) -> bytes:
    # scrypt needs about 128 * n * r * p bytes; allow twice that plus headroom.
    maxmem = 256 * n * r * p + (1 << 20)
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=dklen, maxmem=maxmem
    )


def hash_password(password: str) -> str:
    """Return an encoded scrypt hash for ``password`` with a fresh random salt."""
    if not isinstance(password, str):
        raise TypeError("password must be a string")
    salt = secrets.token_bytes(SALT_BYTES)
    key = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P, KEY_BYTES)
    return f"{ALGORITHM}${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64encode(salt)}${_b64encode(key)}"


def _parse(encoded: str) -> tuple[int, int, int, bytes, bytes] | None:
    """Split an encoded hash into its parts, or None when it is not valid."""
    if not isinstance(encoded, str):
        return None
    parts = encoded.strip().split("$")
    if len(parts) != 6 or parts[0] != ALGORITHM:
        return None
    try:
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        salt = base64.b64decode(parts[4], validate=True)
        key = base64.b64decode(parts[5], validate=True)
    except (ValueError, binascii.Error):
        return None
    n_is_power_of_two = n > 1 and (n & (n - 1)) == 0
    if not (n_is_power_of_two and n <= _MAX_N and 1 <= r <= _MAX_R and 1 <= p <= _MAX_P):
        return None
    if not salt or not (16 <= len(key) <= 64):
        return None
    return n, r, p, salt, key


def is_password_hash(encoded: str) -> bool:
    """True when ``encoded`` has the format produced by `hash_password`."""
    return _parse(encoded) is not None


def verify_password(password: str, encoded: str) -> bool:
    """Check ``password`` against an encoded hash in constant time.

    Returns False (never raises) for a wrong password or a malformed hash.
    """
    if not isinstance(password, str):
        return False
    parsed = _parse(encoded)
    if parsed is None:
        return False
    n, r, p, salt, expected = parsed
    try:
        actual = _scrypt(password, salt, n, r, p, len(expected))
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(actual, expected)
