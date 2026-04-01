from bot.utils.session_keys import feishu_key


class TestFeishuSessionKey:
    def test_p2p(self):
        assert feishu_key("oc_chat1", "ou_user1") == "feishu:oc_chat1:ou_user1"

    def test_group(self):
        assert feishu_key("oc_group1", "ou_user2") == "feishu:oc_group1:ou_user2"
