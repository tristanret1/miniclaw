from unittest.mock import MagicMock, AsyncMock, patch

from bot.config_schema import WhatsAppConfig, GatewayConfig
from bot.utils.session_keys import whatsapp_key


class TestWhatsAppConfig:
    def test_defaults(self):
        cfg = WhatsAppConfig()
        assert cfg.enabled is False
        assert cfg.allow_from == []
        assert cfg.session_db == "workspace/whatsapp_session.db"

    def test_from_dict(self):
        cfg = WhatsAppConfig.from_dict({
            "enabled": True,
            "allow_from": ["+8613800138000"],
            "session_db": "custom/path.db",
        })
        assert cfg.enabled is True
        assert cfg.allow_from == ["+8613800138000"]
        assert cfg.session_db == "custom/path.db"

    def test_from_dict_empty(self):
        cfg = WhatsAppConfig.from_dict({})
        assert cfg.enabled is False

    def test_gateway_config_includes_whatsapp(self):
        gw = GatewayConfig.from_dict({"whatsapp": {"enabled": True}})
        assert gw.whatsapp.enabled is True


class TestWhatsAppSessionKey:
    def test_basic(self):
        assert whatsapp_key("8613800138000") == "whatsapp:8613800138000"

    def test_different_numbers(self):
        assert whatsapp_key("1234567890") == "whatsapp:1234567890"


class TestWhatsAppHelpers:
    def test_jid_to_phone(self):
        from bot.gateway.whatsapp import _jid_to_phone
        jid = MagicMock(User="8613800138000")
        assert _jid_to_phone(jid) == "8613800138000"

    def test_jid_to_phone_string(self):
        from bot.gateway.whatsapp import _jid_to_phone
        assert _jid_to_phone("8613800138000@s.whatsapp.net") == "8613800138000"

    def test_chunk_message_short(self):
        from bot.gateway.whatsapp import _chunk_message
        assert _chunk_message("hello") == ["hello"]

    def test_chunk_message_long(self):
        from bot.gateway.whatsapp import _chunk_message
        text = "a" * 5000
        chunks = _chunk_message(text, limit=4096)
        assert len(chunks) == 2
        assert len(chunks[0]) == 4096
        assert len(chunks[1]) == 904
        assert "".join(chunks) == text

    def test_chunk_message_exact(self):
        from bot.gateway.whatsapp import _chunk_message
        text = "a" * 4096
        assert _chunk_message(text) == [text]
