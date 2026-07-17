import hashlib
import os
import secrets
import struct
import zlib

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def aes_cbc_encrypt(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    """AES-128-CBC with no padding, returning a buffer of the same length."""
    if len(plaintext) % 16:
        raise ValueError("plaintext must be a multiple of 16 bytes")
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    return encryptor.update(plaintext) + encryptor.finalize()


def aes_cbc_decrypt(key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    """AES-128-CBC with no padding."""
    if len(ciphertext) % 16:
        raise ValueError("ciphertext must be a multiple of 16 bytes")
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    return decryptor.update(ciphertext) + decryptor.finalize()


def sha1(data: bytes) -> bytes:
    return hashlib.sha1(data).digest()


def crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def random_bytes(n: int) -> bytes:
    return secrets.token_bytes(n)


def uint32le_to_bytes(value: int) -> bytes:
    return struct.pack("<I", value & 0xFFFFFFFF)


def uint16le_to_bytes(value: int) -> bytes:
    return struct.pack("<H", value & 0xFFFF)


def uint32le_from_bytes(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def uint16le_from_bytes(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<H", data, offset)[0]
