from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from jose import JWTError, jwt

from agent_platform.bootstrap.settings import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
PASSWORD_ENCRYPTION_ALGORITHM = "RSA-OAEP-SHA256"

_password_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_password_public_key = _password_private_key.public_key()
_password_public_key_pem = _password_public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode("ascii")
_password_key_id = hashlib.sha256(
    _password_public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
).hexdigest()[:16]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def get_password_public_key() -> dict[str, str]:
    return {
        "key_id": _password_key_id,
        "algorithm": PASSWORD_ENCRYPTION_ALGORITHM,
        "public_key": _password_public_key_pem,
    }


def decrypt_password(encrypted_password: str, key_id: str) -> str:
    if key_id != _password_key_id:
        raise ValueError("password encryption key mismatch")
    try:
        ciphertext = base64.b64decode(encrypted_password, validate=True)
        plaintext = _password_private_key.decrypt(
            ciphertext,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return plaintext.decode("utf-8")
    except Exception as exc:
        raise ValueError("invalid encrypted password") from exc


def create_access_token(data: dict[str, str], expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, str] | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
