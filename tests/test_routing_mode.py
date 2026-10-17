import unittest
from unittest.mock import MagicMock

from scripts.conversation_agent import (
    ConversationAgent,
    is_infra_query,
    is_lightweight_chat,
    resolve_turn_mode,
)


class RoutingModeTests(unittest.TestCase):
    def test_greetings_are_light(self):
        self.assertTrue(is_lightweight_chat('你好'))
        self.assertTrue(is_lightweight_chat('你好，你是什么模型'))
        self.assertTrue(is_lightweight_chat('who are you'))
        self.assertTrue(is_lightweight_chat('好的'))
        self.assertTrue(is_lightweight_chat('嗯'))
        self.assertTrue(is_lightweight_chat('谢谢'))
        self.assertTrue(is_lightweight_chat('ok'))
        self.assertFalse(is_lightweight_chat('帮我看一下 HCCL 507049'))

    def test_infra_detection(self):
        self.assertTrue(is_infra_query('torch_npu 报错', has_urls=False))
        self.assertTrue(is_infra_query('随便', has_urls=True))
        self.assertTrue(is_infra_query('长文', has_new_artifact=True))
        self.assertTrue(is_infra_query('507049 怎么排查？'))
        self.assertTrue(is_infra_query('查版本'))
        self.assertFalse(is_infra_query('今天天气怎么样', has_urls=False))
        # Sticky context alone must NOT force infra on ack / unrelated long chat
        self.assertFalse(is_infra_query('好的', has_context=True, session_lane='work'))
        self.assertFalse(is_infra_query('今天中午吃什么比较好呢朋友', has_context=True, session_lane='work'))
        # Real follow-up only while work lane is active
        self.assertTrue(is_infra_query('那怎么改？', has_context=True, session_lane='work'))
        self.assertFalse(is_infra_query('那怎么改？', has_context=True, session_lane='chat'))

    def test_resolve_turn_mode_auto_switches(self):
        self.assertEqual(resolve_turn_mode('auto', '好的', True, False, session_lane='work'), 'light')
        self.assertEqual(
            resolve_turn_mode('auto', '那怎么改', True, False, session_lane='work'), 'infra')
        self.assertEqual(
            resolve_turn_mode('auto', '今天天气怎么样啊呀呀', True, False, session_lane='work'),
            'general')
        self.assertEqual(
            resolve_turn_mode('auto', 'x', False, False, has_new_artifact=True), 'infra')
        self.assertEqual(resolve_turn_mode('chat', '帮我看 torch_npu', False, False), 'general')
        self.assertEqual(resolve_turn_mode('work', '随便聊聊天气', False, False), 'infra')

    def test_greeting_skips_knowledge_search(self):
        class Client:
            def chat_with_history(self, messages, **kwargs):
                return '我是 ReviewAgent。'

        knowledge = MagicMock()
        knowledge.warnings = []
        knowledge.search = MagicMock(return_value=[{'title': 'should not run'}])
        agent = ConversationAgent(Client(), knowledge, MagicMock())
        reply = agent.answer('你好，你是什么模型')
        self.assertIn('ReviewAgent', reply)
        knowledge.search.assert_not_called()

    def test_auto_ack_after_work_leaves_infra_tools(self):
        class Client:
            def chat_with_history(self, messages, **kwargs):
                return '好的，有需要再说。'

        knowledge = MagicMock()
        knowledge.warnings = []
        knowledge.search = MagicMock(return_value=[{'title': 'should not run'}])
        agent = ConversationAgent(Client(), knowledge, MagicMock())
        agent.contexts = [{
            'type': 'paste', 'title': '7月社区任务', 'body': 'x' * 500,
            'url': '(pasted-local)', 'state': 'local', 'host': 'paste',
            'comments': [], 'files': [], 'reviews': [], 'inline_comments': [],
            'warnings': [],
        }]
        agent.session_lane = 'work'
        agent.answer('好的')
        knowledge.search.assert_not_called()
        self.assertEqual(agent.session_lane, 'chat')

    def test_auto_followup_stays_work(self):
        class Client:
            def chat_with_history(self, messages, **kwargs):
                return '方案如下'

        knowledge = MagicMock()
        knowledge.warnings = []
        knowledge.search = MagicMock(return_value=[])
        agent = ConversationAgent(Client(), knowledge, MagicMock())
        agent.contexts = [{
            'type': 'paste', 'title': 'task', 'body': 'body',
            'url': '(pasted-local)', 'state': 'local', 'host': 'paste',
            'comments': [], 'files': [], 'reviews': [], 'inline_comments': [],
            'warnings': [],
        }]
        agent.session_lane = 'work'
        agent.answer('那怎么改？')
        knowledge.search.assert_called()
        self.assertEqual(agent.session_lane, 'work')

    def test_chat_mode_command_skips_infra_even_for_npu(self):
        class Client:
            def chat_with_history(self, messages, **kwargs):
                return messages[-1]['content']

        knowledge = MagicMock()
        knowledge.warnings = []
        knowledge.search = MagicMock(return_value=[])
        agent = ConversationAgent(Client(), knowledge, MagicMock())
        agent.set_chat_mode('chat')
        agent.answer('torch_npu 报错怎么办')
        knowledge.search.assert_not_called()

    def test_work_mode_forces_infra_tools(self):
        class Client:
            def chat_with_history(self, messages, **kwargs):
                return 'ok'

        knowledge = MagicMock()
        knowledge.warnings = []
        knowledge.search = MagicMock(return_value=[])
        agent = ConversationAgent(Client(), knowledge, MagicMock())
        agent.set_chat_mode('work')
        agent.answer('今天天气怎么样')
        knowledge.search.assert_called()


if __name__ == '__main__':
    unittest.main()
