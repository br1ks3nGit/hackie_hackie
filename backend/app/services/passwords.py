import hashlib
import secrets

SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SCRYPT_MAXMEM = 64 * 1024 * 1024
SALT_BYTES = 16
SCHEME = "scrypt"


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode(), salt=salt, n=n, r=r, p=p, dklen=SCRYPT_DKLEN, maxmem=SCRYPT_MAXMEM
    )


def hash_password(password: str) -> str:
    """Return `scrypt:<n>:<r>:<p>:<salt_hex>:<hash_hex>` (no `$`, safe for docker compose)."""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _derive(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"{SCHEME}:{SCRYPT_N}:{SCRYPT_R}:{SCRYPT_P}:{salt.hex()}:{digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check; a malformed stored hash verifies as False."""
    try:
        scheme, n, r, p, salt_hex, hash_hex = stored.split(":")
        if scheme != SCHEME:
            return False
        expected = bytes.fromhex(hash_hex)
        actual = _derive(password, bytes.fromhex(salt_hex), int(n), int(r), int(p))
    except ValueError:
        return False
    return secrets.compare_digest(actual, expected)
