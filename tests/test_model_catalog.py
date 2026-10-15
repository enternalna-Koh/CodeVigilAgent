import unittest

from scripts.model_catalog import (
    apply_target_to_config,
    gateway_changed,
    resolve_model_request,
)


class ModelCatalogTests(unittest.TestCase):
    def test_resolve_vendor_glm(self):
        t = resolve_model_request('glm')
        self.assertTrue(t['ok'])
        self.assertEqual(t['file_provider'], 'glm')
        self.assertEqual(t['model'], 'glm-4-flash')
        self.assertEqual(t['base_url'], '')

    def test_resolve_exact_model(self):
        t = resolve_model_request('glm-4-plus')
        self.assertEqual(t['file_provider'], 'glm')
        self.assertEqual(t['model'], 'glm-4-plus')

    def test_resolve_minimax(self):
        t = resolve_model_request('MiniMax-M1')
        self.assertEqual(t['file_provider'], 'openai')
        self.assertIn('minimax', t['base_url'])

    def test_gateway_changed_minimax_to_glm(self):
        current = {
            'provider': 'openai',
            'base_url': 'https://api.minimax.chat/v1',
            'model': 'MiniMax-Text-01',
        }
        target = resolve_model_request('glm')
        self.assertTrue(gateway_changed(current, target))

    def test_gateway_same_minimax_model_swap(self):
        current = {
            'provider': 'openai',
            'base_url': 'https://api.minimax.chat/v1',
            'model': 'MiniMax-Text-01',
        }
        target = resolve_model_request('MiniMax-M1')
        self.assertFalse(gateway_changed(current, target))

    def test_apply_clears_foreign_base_url(self):
        data = {
            'provider': 'openai',
            'base_url': 'https://api.minimax.chat/v1',
            'api_key': 'old',
            'model': 'MiniMax-Text-01',
        }
        target = resolve_model_request('glm')
        out = apply_target_to_config(data, target, api_key='new-glm-key')
        self.assertEqual(out['provider'], 'glm')
        self.assertEqual(out['model'], 'glm-4-flash')
        self.assertEqual(out['base_url'], '')
        self.assertEqual(out['api_key'], 'new-glm-key')


if __name__ == '__main__':
    unittest.main()
