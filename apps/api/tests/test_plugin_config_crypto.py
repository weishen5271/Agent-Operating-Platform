from __future__ import annotations

import pytest

from agent_platform.infrastructure.config_crypto import PluginConfigCrypto


def test_plugin_config_crypto_encrypts_and_decrypts_nested_secrets() -> None:
    crypto = PluginConfigCrypto(key_material="test-only-key")
    original = {
        "endpoint": "https://cmms.local",
        "secrets": {
            "cmms_token": "token-123456",
            "nested": {"api_key": "key-abcdef"},
        },
        "timeout_ms": 5000,
    }

    encrypted = crypto.encrypt_config(original)
    decrypted = crypto.decrypt_config(encrypted)

    assert encrypted["endpoint"] == "https://cmms.local"
    assert encrypted["timeout_ms"] == 5000
    assert encrypted["secrets"]["cmms_token"]["__aop_encrypted_secret__"] is True
    assert encrypted["secrets"]["cmms_token"]["ciphertext"] != "token-123456"
    assert encrypted["secrets"]["nested"]["api_key"]["ciphertext"] != "key-abcdef"
    assert decrypted == original
    assert original["secrets"]["cmms_token"] == "token-123456"


def test_plugin_config_crypto_keeps_legacy_plaintext_readable() -> None:
    crypto = PluginConfigCrypto(key_material="test-only-key")
    legacy = {"secrets": {"cmms_token": "legacy-token"}}

    assert crypto.decrypt_config(legacy) == legacy


def test_plugin_config_crypto_rejects_wrong_key_for_encrypted_secret() -> None:
    encrypted = PluginConfigCrypto(key_material="first-key").encrypt_config(
        {"secrets": {"cmms_token": "token-123456"}}
    )

    with pytest.raises(ValueError, match="Unable to decrypt"):
        PluginConfigCrypto(key_material="second-key").decrypt_config(encrypted)
