import getpass
import os
import struct

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

try:
    import keyring
    _KEYRING_AVAILABLE = True
except Exception:
    _KEYRING_AVAILABLE = False

from .exceptions import DecryptionError

KEYCHAIN_SERVICE = "ossnap"
KEYCHAIN_ACCOUNT = "encryption-password"
SALT_SIZE = 16
PBKDF2_ITERATIONS = 600_000

# ossnap <= 0.1.5 stored ``salt || fernet_token``. New snapshots include a
# versioned header so KDF upgrades can preserve compatibility with old files.
MAGIC = b"OSSNAP"
FORMAT_VERSION = 1
KDF_PBKDF2_SHA256 = 1
HEADER = struct.Struct(">6sBBI")  # magic, version, KDF id, PBKDF2 iterations


def get_password_if_exists() -> str | None:
    if _KEYRING_AVAILABLE:
        return keyring.get_password(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)
    return None


def get_or_create_password() -> str:
    if _KEYRING_AVAILABLE:
        pw = keyring.get_password(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)
        if pw:
            return pw
    pw = getpass.getpass("Encryption password: ")
    if _KEYRING_AVAILABLE:
        keyring.set_password(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT, pw)
    return pw


def set_password(pw: str) -> None:
    if _KEYRING_AVAILABLE:
        keyring.set_password(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT, pw)


def _derive_key(password: str, salt: bytes) -> bytes:
    return _derive_key_with_iterations(password, salt, PBKDF2_ITERATIONS)


def _derive_key_with_iterations(password: str, salt: bytes, iterations: int) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def encrypt_bytes(data: bytes, password: str) -> bytes:
    salt = os.urandom(SALT_SIZE)
    key = _derive_key(password, salt)
    token = Fernet(key).encrypt(data)
    return HEADER.pack(MAGIC, FORMAT_VERSION, KDF_PBKDF2_SHA256, PBKDF2_ITERATIONS) + salt + token


def decrypt_bytes(data: bytes, password: str) -> bytes:
    if data.startswith(MAGIC):
        if len(data) < HEADER.size + SALT_SIZE:
            raise DecryptionError("Encrypted file is truncated.")
        magic, version, kdf_id, iterations = HEADER.unpack(data[:HEADER.size])
        if magic != MAGIC or version != FORMAT_VERSION:
            raise DecryptionError("Unsupported encrypted file format.")
        if kdf_id != KDF_PBKDF2_SHA256:
            raise DecryptionError("Unsupported key derivation algorithm.")
        # Header bytes are untrusted input. Only accept the cost parameters
        # supported by this format to prevent a malicious snapshot from causing
        # an expensive arbitrary PBKDF2 computation before authentication.
        if iterations != PBKDF2_ITERATIONS:
            raise DecryptionError("Unsupported key derivation parameters.")
        salt = data[HEADER.size:HEADER.size + SALT_SIZE]
        token = data[HEADER.size + SALT_SIZE:]
    else:
        if len(data) < SALT_SIZE:
            raise DecryptionError("Encrypted file is truncated.")
        # Legacy format from ossnap <= 0.1.5: salt || fernet_token.
        salt = data[:SALT_SIZE]
        token = data[SALT_SIZE:]
        iterations = PBKDF2_ITERATIONS

    key = _derive_key_with_iterations(password, salt, iterations)
    try:
        return Fernet(key).decrypt(token)
    except InvalidToken:
        raise DecryptionError("Wrong password or corrupted file.")


def encrypt_file(src, dst, password: str) -> None:
    from pathlib import Path
    data = Path(src).read_bytes()
    encrypted = encrypt_bytes(data, password)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    Path(dst).write_bytes(encrypted)


def decrypt_file(src, dst, password: str) -> None:
    from pathlib import Path
    data = Path(src).read_bytes()
    decrypted = decrypt_bytes(data, password)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    Path(dst).write_bytes(decrypted)
