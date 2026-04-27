from __future__ import annotations

import base64
import copy
from hashlib import sha256
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from agent_platform.bootstrap.settings import settings

_SECRET_MARKER = "__aop_encrypted_secret__"
_SECRET_VERSION = "fernet:v1"


class PluginConfigCrypto:
    """Encrypt and decrypt secret values inside plugin_config JSON payloads."""

    def __init__(self, *, key_material: str | None = None) -> None:
        material = key_material or settings.plugin_config_encryption_key or settings.secret_key
        key = base64.urlsafe_b64encode(sha256(material.encode("utf-8")).digest())
        self._fernet = Fernet(key)

    def encrypt_config(self, config: dict[str, Any]) -> dict[str, Any]:
        encrypted = copy.deepcopy(config)
        secrets = encrypted.get("secrets")
        if isinstance(secrets, dict):
            encrypted["secrets"] = self._encrypt_secret_tree(secrets)
        return encrypted

    def decrypt_config(self, config: dict[str, Any]) -> dict[str, Any]:
        decrypted = copy.deepcopy(config)
        secrets = decrypted.get("secrets")
        if isinstance(secrets, dict):
            decrypted["secrets"] = self._decrypt_secret_tree(secrets)
        return decrypted

    def _encrypt_secret_tree(self, value: Any) -> Any:
        if isinstance(value, dict):
            if self._is_encrypted_secret(value):
                return value
            return {key: self._encrypt_secret_tree(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._encrypt_secret_tree(item) for item in value]
        if isinstance(value, str):
            return {
                _SECRET_MARKER: True,
                "version": _SECRET_VERSION,
                "ciphertext": self._fernet.encrypt(value.encode("utf-8")).decode("ascii"),
            }
        return value

    def _decrypt_secret_tree(self, value: Any) -> Any:
        if isinstance(value, dict):
            if self._is_encrypted_secret(value):
                ciphertext = str(value.get("ciphertext") or "")
                try:
                    return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
                except (InvalidToken, ValueError) as exc:
                    raise ValueError("Unable to decrypt plugin_config secret") from exc
            return {key: self._decrypt_secret_tree(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._decrypt_secret_tree(item) for item in value]
        return value

    @staticmethod
    def _is_encrypted_secret(value: dict[str, Any]) -> bool:
        return value.get(_SECRET_MARKER) is True and value.get("version") == _SECRET_VERSION
