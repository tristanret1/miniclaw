from unittest.mock import MagicMock, AsyncMock, patch

from bot.config_schema import FeishuConfig, GatewayConfig
from bot.utils.session_keys import feishu_key


class TestFeishuConfig:
    def test_defaults(self):
        cfg = FeishuConfig()
        assert cfg.enabled is False
        assert cfg.allow_from == []

    def test_from_dict(self):
        cfg = FeishuConfig.from_dict({
            "enabled": True,
            "allow_from": ["oc_abc123"],
        })
        assert cfg.enabled is True
        assert cfg.allow_from == ["oc_abc123"]

    def test_from_dict_empty(self):
        cfg = FeishuConfig.from_dict({})
        assert cfg.enabled is False

    def test_gateway_config_includes_feishu(self):
        gw = GatewayConfig.from_dict({"feishu": {"enabled": True}})
        assert gw.feishu.enabled is True


class TestFeishuSessionKey:
    def test_p2p(self):
        assert feishu_key("oc_chat1", "ou_user1") == "feishu:oc_chat1:ou_user1"

    def test_group(self):
        assert feishu_key("oc_group1", "ou_user2") == "feishu:oc_group1:ou_user2"


class TestFeishuMessageParsing:
    def test_parse_text_content(self):
        from bot.gateway.feishu import _parse_text_content
        assert _parse_text_content('{"text":"hello world"}') == "hello world"

    def test_parse_text_content_empty(self):
        from bot.gateway.feishu import _parse_text_content
        assert _parse_text_content('{"text":""}') == ""

    def test_parse_text_content_invalid_json(self):
        from bot.gateway.feishu import _parse_text_content
        assert _parse_text_content("not json") == "not json"

    def test_strip_bot_mention(self):
        from bot.gateway.feishu import _strip_bot_mention
        text = "@_user_1 hello"
        mentions = [MagicMock(key="@_user_1", id=MagicMock(open_id="ou_bot123"))]
        result = _strip_bot_mention(text, mentions, "ou_bot123")
        assert result == "hello"

    def test_strip_bot_mention_no_mentions(self):
        from bot.gateway.feishu import _strip_bot_mention
        assert _strip_bot_mention("hello", None, "ou_bot") == "hello"

    def test_strip_bot_mention_keeps_user_mentions(self):
        from bot.gateway.feishu import _strip_bot_mention
        text = "@_user_1 @_user_2 hello"
        mentions = [
            MagicMock(key="@_user_1", id=MagicMock(open_id="ou_bot")),
            MagicMock(key="@_user_2", id=MagicMock(open_id="ou_other")),
        ]
        result = _strip_bot_mention(text, mentions, "ou_bot")
        assert "@_user_2" in result
        assert "@_user_1" not in result


class TestFeishuSend:
    async def test_send_no_client(self):
        from bot.gateway.feishu import send_feishu_message
        import bot.gateway.feishu as mod
        mod._api_client = None
        result = await send_feishu_message("oc_123", "hello")
        assert "Error" in result
