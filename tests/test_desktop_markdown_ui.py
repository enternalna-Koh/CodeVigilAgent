"""回归：Windows 桌面聊天的 Markdown、可复制文字及重新排版。"""
from pathlib import Path
import importlib.util
import subprocess
import sys
import unittest
from unittest.mock import patch

try:
    import tkinter as tk
except ImportError:
    tk = None

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop_py"
if str(DESKTOP) not in sys.path:
    sys.path.insert(0, str(DESKTOP))

if tk is not None:
    from md_render import MarkdownBlock, UserBubble
    from ui_kit import ScrollArea


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if tk is None:
            raise unittest.SkipTest("Python 未安装 tkinter")
        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"无法打开图形界面：{exc}")

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        # Aqua Tk 的进程级应用对象不能按每个用例反复销毁；复用同一根窗口，
        # 每例仍创建全新控件并在结束时移除，保留真实事件及剪贴板断言。
        self.root.geometry("700x460+120+120")
        self.area = ScrollArea(self.root)
        self.area.pack(fill="both", expand=True)
        self.font = ("TkDefaultFont", 12, "normal")
        self.root.update()

    def tearDown(self):
        for child in self.root.winfo_children():
            child.destroy()
        self.root.update_idletasks()

    def block(self, content, **kwargs):
        block = MarkdownBlock(self.area.body, content, self.font, 500, **kwargs)
        block.pack(fill="x")
        self.root.update()
        return block

    def tag_at(self, block, value):
        index = block.text.search(value, "1.0", stopindex="end")
        self.assertTrue(index, value)
        return block.text.tag_names(index)

    def test_common_markdown_and_tables(self):
        raw = ("# 标题 **重点**\n\n这是 **加粗** 和 *斜体*，还有 `代码`。\n"
               "- 列表 **第一项**\n1. 序号\n> 引用\n"
               "| 名称 | 数量 |\n| --- | ---: |\n| 苹果 | **2** |\n"
               "```python\nprint('hi')\n```\n[网站](https://example.test)")
        block = self.block(raw)
        displayed = block.text.get("1.0", "end-1c")
        self.assertIn("标题 重点", displayed)
        self.assertIn("这是 加粗 和 斜体，还有 代码。", displayed)
        self.assertIn("名称  │  数量\n苹果  │  2", displayed)
        self.assertIn("print('hi')", displayed)
        self.assertIn("网站 (https://example.test)", displayed)
        self.assertNotIn("**", displayed)
        for value, tag in (("标题", "h1"), ("重点", "bold"), ("加粗", "bold"),
                           ("斜体", "italic"), ("代码", "code"), ("列表", "bullet"),
                           ("引用", "quote"), ("名称", "table_header"),
                           ("print('hi')", "codeblock"), ("网站", "link")):
            self.assertIn(tag, self.tag_at(block, value), value)
        self.assertEqual(str(block.text.cget("state")), "disabled")

    def test_escaped_markers_nested_styles_and_line_endings(self):
        block = self.block(r"\*字面星号\* **一段 *斜粗体* 文字**" + "\n\n")
        self.assertEqual(block.text.get("1.0", "end-1c"), "*字面星号* 一段 斜粗体 文字\n\n")
        tags = self.tag_at(block, "斜粗体")
        self.assertIn("bold", tags)
        self.assertIn("bold_italic", tags)

    def test_user_bubble_keeps_plain_text_and_round_background(self):
        original = "用户 **原始文字**\n第二行"
        bubble = UserBubble(self.area.body, original, self.font, 420)
        bubble.pack(fill="x")
        self.root.update()
        self.assertEqual(bubble.text.get("1.0", "end-1c"), original)
        self.assertEqual(str(bubble.text.cget("state")), "disabled")
        self.assertTrue(bubble._canvas.find_withtag("bubble_bg"))
        self.assertEqual(str(bubble._canvas.pack_info()["anchor"]), "e")

    def test_keyboard_selection_copy_and_readonly(self):
        block = self.block("**加粗的文字**")
        bubble = UserBubble(self.area.body, "用户原文", self.font, 420)
        bubble.pack(fill="x")
        self.root.update()
        modifier = "Command" if self.root.tk.call("tk", "windowingsystem") == "aqua" else "Control"
        for obj, expected in ((block, "加粗的文字"), (bubble, "用户原文")):
            obj.text.focus_force()
            self.root.update()
            obj.text.event_generate(f"<{modifier}-KeyPress-a>")
            obj.text.event_generate(f"<{modifier}-KeyPress-c>")
            self.root.update()
            self.assertEqual(self.root.clipboard_get(), expected)
            obj.text.event_generate("<KeyPress-X>")
            self.root.update()
            self.assertEqual(obj.text.get("1.0", "end-1c"), expected)

    def test_clipboard_selected_and_all_for_both_message_types(self):
        block = self.block("**回复文字**")
        bubble = UserBubble(self.area.body, "用户消息", self.font, 420)
        bubble.pack(fill="x")
        self.root.update()
        with patch.object(tk.Misc, "clipboard_clear", autospec=True) as clear, \
             patch.object(tk.Misc, "clipboard_append", autospec=True) as append:
            for obj, expected in ((block, "回复文字"), (bubble, "用户消息")):
                obj.text.tag_add("sel", "1.0", "1.2")
                obj.copy_selection()
                self.assertEqual(append.call_args.args[1], expected[:2])
                obj.copy_all()
                self.assertEqual(append.call_args.args[1], expected)
                obj.text.tag_remove("sel", "1.0", "end")
                calls = clear.call_count
                obj.copy_selection()
                self.assertEqual(clear.call_count, calls)
            block.copy_source()
            self.assertEqual(append.call_args.args[1], "**回复文字**")

    def test_long_content_and_resize_do_not_clip(self):
        body = "# 大标题\n\n" + "中英混排 **加粗** word " * 220
        block = self.block(body)
        bubble = UserBubble(self.area.body, "长消息 " * 220, self.font, 500)
        bubble.pack(fill="x")
        self.root.update()
        for width in (320, 650):
            self.root.geometry(f"{width}x460+120+120")
            bubble.set_max_width(width - 40)
            self.root.update()
            self.root.update_idletasks()
            for widget in (block.text, bubble.text):
                self.assertEqual(widget.yview(), (0.0, 1.0))
                required = int(widget.tk.call(widget._w, "count", "-update", "-ypixels",
                                               "1.0", "end"))
                self.assertGreaterEqual(widget.winfo_height(), required)

    def test_wheel_moves_outer_scroll_not_inner_text(self):
        block = self.block("滚轮测试 " * 450)
        self.area.canvas.yview_moveto(0.0)
        self.root.update()
        before = self.area.canvas.yview()[0]
        with patch.object(self.area, "_pointer_inside", return_value=True):
            block.text.event_generate("<MouseWheel>", delta=-120)
            self.root.update()
        self.assertGreater(self.area.canvas.yview()[0], before)
        self.assertEqual(block.text.yview(), (0.0, 1.0))

    def test_user_bubble_ignores_transient_narrow_width(self):
        original = "长消息 " * 800
        bubble = UserBubble(self.area.body, original, self.font, 400)
        bubble.pack(fill="x")
        self.root.update()
        height = bubble._canvas.winfo_height()
        with patch.object(bubble._canvas, "configure", wraps=bubble._canvas.configure) as configure:
            bubble.text.place_configure(width=2)
            self.root.update()
            self.assertEqual(bubble.text.winfo_width(), 2)
            configure.assert_not_called()
        self.assertEqual(bubble._canvas.winfo_height(), height)
        bubble.set_max_width(280)
        self.root.update()
        self.assertEqual(bubble.text.get("1.0", "end-1c"), original)
        self.assertEqual(bubble.text.yview(), (0.0, 1.0))
        required = int(bubble.text.tk.call(bubble.text._w, "count", "-update", "-ypixels",
                                          "1.0", "end"))
        self.assertGreaterEqual(bubble.text.winfo_height(), required)

    def test_destroy_cancels_pending_message_layout(self):
        for message_type in (MarkdownBlock, UserBubble):
            for mapped in (False, True):
                with self.subTest(message_type=message_type.__name__, mapped=mapped):
                    message = message_type(self.area.body, "长消息 " * 800, self.font, 400)
                    if mapped:
                        message.pack(fill="x")
                        self.root.update()
                    message._schedule_fit()
                    job = message._fit_job
                    self.assertIsNotNone(job)
                    message.destroy()
                    self.assertNotIn(job, self.root.tk.splitlist(self.root.tk.call("after", "info")))
                    self.root.update()

    def test_wheel_over_user_bubble_moves_outer_scroll(self):
        original = "长消息 " * 800
        bubble = UserBubble(self.area.body, original, self.font, 400)
        bubble.pack(fill="x")
        self.root.update()
        self.area.canvas.yview_moveto(0.0)
        self.root.update()
        before = self.area.canvas.yview()[0]
        with patch.object(self.area, "_pointer_inside", return_value=True):
            bubble.text.event_generate("<MouseWheel>", delta=-120)
            self.root.update()
        self.assertGreater(self.area.canvas.yview()[0], before)
        self.assertEqual(bubble.text.yview(), (0.0, 1.0))
        bubble.copy_all()
        self.assertEqual(self.root.clipboard_get(), original)
        self.area.canvas.yview_moveto(1.0)
        self.root.update()
        self.assertEqual(self.area.canvas.yview()[1], 1.0)
        last_line = bubble.text.dlineinfo("end-1c")
        self.assertIsNotNone(last_line)
        self.assertLessEqual(last_line[1] + last_line[3], bubble.text.winfo_height())

    def test_report_text_is_verbatim(self):
        raw = "报告 **原样**\n下一行\n"
        block = self.block(raw, markdown=False)
        self.assertEqual(block.text.get("1.0", "end-1c"), raw)
        self.assertIn("codeblock", self.tag_at(block, "报告"))

    def test_synthetic_historical_conversation_redraw(self):
        # App 自己是 Tk 根窗口；独立进程保留真实重绘，避免破坏 Aqua 的共享应用状态。
        result = subprocess.run(
            [sys.executable, "-c",
             "import runpy, sys; namespace = runpy.run_path(sys.argv[1]); "
             "namespace['RenderTests']()._assert_historical_redraw()",
             str(Path(__file__).resolve())],
            capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def _assert_historical_redraw(self):
        spec = importlib.util.spec_from_file_location("desktop_py_app", DESKTOP / "app.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        App = module.App
        with patch.object(App, "load_sessions"), patch.object(App, "show_welcome"):
            app = App()
            app.update()
            try:
                session = {"name": "md-test", "title": "测试", "messages": [
                    {"role": "user", "content": "问题 **原文**"},
                    {"role": "assistant", "content": "回答 **重点**", "elapsed_ms": 1200},
                ]}
                app._apply_session("md-test", session, {"ok": True}, "")
                app.update()
                self.assertEqual(app.messages[0]["content"], "问题 **原文**")
                self.assertEqual(app.messages[1]["content"], "回答 **重点**")
                self.assertEqual(app._bubbles[0].text.get("1.0", "end-1c"), "问题 **原文**")
                self.assertEqual(app._agent_texts[0].text.get("1.0", "end-1c"), "回答 重点")
                app.rerender()
                app.update()
                self.assertEqual(app._agent_texts[0].text.get("1.0", "end-1c"), "回答 重点")
                self.assertEqual(app.messages[1]["content"], "回答 **重点**")
            finally:
                for job in app.tk.splitlist(app.tk.call("after", "info")):
                    app.after_cancel(job)
                app.destroy()


if __name__ == "__main__":
    unittest.main()
