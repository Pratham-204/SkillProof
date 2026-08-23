import secrets

from cryptography.fernet import Fernet, InvalidToken

from skillproof.config import get_settings


class TokenDecryptionError(Exception):
    pass


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def _fernet() -> Fernet:
    return Fernet(get_settings().token_encryption_key.encode())


def encrypt_token(plaintext_token: str) -> str:
    return _fernet().encrypt(plaintext_token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    try:
        return _fernet().decrypt(encrypted_token.encode()).decode()
    except InvalidToken as exc:
        raise TokenDecryptionError("Stored GitHub token could not be decrypted") from exc
