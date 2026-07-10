from cryptography.fernet import Fernet
import struct

from ossnap import crypto
from ossnap.exceptions import DecryptionError


def test_new_ciphertext_has_metadata_and_round_trips():
    encrypted = crypto.encrypt_bytes(b"secret", "correct horse battery staple")

    assert encrypted.startswith(crypto.MAGIC)
    assert crypto.decrypt_bytes(encrypted, "correct horse battery staple") == b"secret"


def test_legacy_ciphertext_still_decrypts():
    password = "correct horse battery staple"
    salt = b"a" * crypto.SALT_SIZE
    legacy = salt + Fernet(crypto._derive_key(password, salt)).encrypt(b"legacy secret")

    assert crypto.decrypt_bytes(legacy, password) == b"legacy secret"


def test_tampered_ciphertext_is_rejected():
    encrypted = bytearray(crypto.encrypt_bytes(b"secret", "password"))
    encrypted[-1] ^= 1

    try:
        crypto.decrypt_bytes(bytes(encrypted), "password")
    except DecryptionError:
        pass
    else:
        raise AssertionError("Tampered ciphertext was accepted")


def test_unsupported_kdf_cost_is_rejected_before_deriving_a_key():
    encrypted = crypto.encrypt_bytes(b"secret", "password")
    modified_header = struct.pack(
        ">6sBBI", crypto.MAGIC, crypto.FORMAT_VERSION, crypto.KDF_PBKDF2_SHA256, 2_000_000_000
    )

    try:
        crypto.decrypt_bytes(modified_header + encrypted[crypto.HEADER.size:], "password")
    except DecryptionError as error:
        assert "parameters" in str(error)
    else:
        raise AssertionError("Unsupported KDF parameters were accepted")
