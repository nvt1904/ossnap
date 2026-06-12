import getpass
import os

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
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def encrypt_bytes(data: bytes, password: str) -> bytes:
    salt = os.urandom(SALT_SIZE)
    key = _derive_key(password, salt)
    token = Fernet(key).encrypt(data)
    return salt + token


def decrypt_bytes(data: bytes, password: str) -> bytes:
    salt = data[:SALT_SIZE]
    token = data[SALT_SIZE:]
    key = _derive_key(password, salt)
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
