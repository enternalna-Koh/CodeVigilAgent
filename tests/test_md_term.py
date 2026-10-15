import unittest

from scripts.md_term import render_markdown, _strip_ansi


class MdTermTests(unittest.TestCase):
    def test_headings_and_bold(self):
        lines = render_markdown('### 标题\n\n这是 **粗体** 和 `code`')
        joined = '\n'.join(_strip_ansi(l) for l in lines)
        self.assertIn('标题', joined)
        self.assertNotIn('###', joined)
        self.assertNotIn('**', joined)
        self.assertIn('粗体', joined)
        self.assertIn('code', joined)

    def test_lists(self):
        lines = render_markdown('- a\n- b\n1. c')
        plain = [_strip_ansi(l) for l in lines]
        self.assertTrue(any('a' in p for p in plain))
        self.assertTrue(any('c' in p for p in plain))


if __name__ == '__main__':
    unittest.main()
