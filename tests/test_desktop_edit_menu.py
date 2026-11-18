"""输入栏右键菜单：剪切 / 复制 / 粘贴 / 全选。

两级验证：
1) 菜单项转发的是 tk 自带的虚拟事件（全平台确定，不依赖窗口系统）；
2) Windows 上真实读写剪贴板，证明四项功能实际生效。
"""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

try:
    import tkinter as tk
except ModuleNotFoundError:
    tk = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "desktop_py"))
sys.path.insert(0, str(ROOT))
if tk is not None:
    import edit_menu
    import app as desktop


def _label(menu, index):
    return "---" if menu.type(index) == "separator" else menu.entrycget(index, "label")


@unittest.skipIf(tk is None, '当前 Python 未安装 tkinter')
class EditMenuTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
            self.root.withdraw()
        except tk.TclError as exc:
            self.skipTest(f'当前环境没有可用图形显示：{exc}')
        self.text = tk.Text(self.root)
        self.text.pack()
        self.text.insert("1.0", "第一行\n第二行")
        self.menu = edit_menu.attach_edit_menu(self.text)
        self.root.update()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    # ------------------------------------------------------------ 结构
    def test_menu_items_match_request(self):
        labels = [_label(self.menu, i) for i in range(self.menu.index("end") + 1)]
        self.assertEqual(labels, ["剪切", "复制", "粘贴", "---", "全选"])

    def test_right_click_is_bound(self):
        self.assertTrue(self.text.bind("<Button-3>"))

    def test_menu_forwards_tk_virtual_events(self):
        with patch.object(self.text, "event_generate") as generate:
            for index in (0, 1, 2):
                self.menu._invoke(index)
        self.assertEqual([call.args[0] for call in generate.call_args_list],
                         ["<<Cut>>", "<<Copy>>", "<<Paste>>"])

    def test_entry_select_all_still_forwards_virtual_event(self):
        entry = tk.Entry(self.root)
        menu = edit_menu.attach_edit_menu(entry)
        with patch.object(entry, "event_generate") as generate:
            menu._invoke(4)
        generate.assert_called_once_with("<<SelectAll>>")

    # ------------------------------------------------------------ 行为
    def test_select_all_covers_whole_text(self):
        self.menu._invoke(4)
        self.assertEqual(self.text.index("sel.first"), "1.0")
        self.assertEqual(self.text.index("sel.last"), self.text.index("end-1c"))

    def test_states_follow_selection(self):
        self.menu.sync_state()
        self.assertEqual(str(self.menu.entrycget(0, "state")), "disabled")
        self.assertEqual(str(self.menu.entrycget(1, "state")), "disabled")
        self.text.tag_add("sel", "1.0", "1.2")
        self.menu.sync_state()
        self.assertEqual(str(self.menu.entrycget(0, "state")), "normal")
        self.assertEqual(str(self.menu.entrycget(1, "state")), "normal")

    def test_readonly_widget_disables_cut_and_paste(self):
        self.text.tag_add("sel", "1.0", "1.2")
        self.text.configure(state="disabled")
        self.menu.sync_state()
        self.assertEqual(str(self.menu.entrycget(0, "state")), "disabled")  # 剪切
        self.assertEqual(str(self.menu.entrycget(1, "state")), "normal")    # 复制
        self.assertEqual(str(self.menu.entrycget(2, "state")), "disabled")  # 粘贴

    def test_right_click_keeps_existing_selection(self):
        self.text.tag_add("sel", "1.0", "1.2")
        with patch.object(self.menu, "tk_popup"):
            self.menu._popup(SimpleNamespace(x=5, y=5, x_root=100, y_root=100))
        self.assertEqual(self.text.index("sel.first"), "1.0")
        self.assertEqual(self.text.index("sel.last"), "1.2")

    def test_right_click_moves_insert_when_no_selection(self):
        self.text.mark_set("insert", "end-1c")
        with patch.object(self.menu, "tk_popup"):
            self.menu._popup(SimpleNamespace(x=0, y=0, x_root=1, y_root=1))
        self.assertEqual(self.text.index("insert"), "1.0")

    # ------------------------------------------------------ 真实剪贴板
    @unittest.skipUnless(os.name == "nt", '真实剪贴板只在 Windows 上断言')
    def test_real_copy_cut_paste(self):
        self.text.tag_add("sel", "1.0", "1.2")
        self.menu._invoke(1)                      # 复制
        self.root.update()
        self.assertEqual(self.text.clipboard_get(), "第一")

        self.text.delete("1.0", "end")
        self.text.clipboard_clear()
        self.text.clipboard_append("粘贴进来的")
        self.root.update()
        self.menu._invoke(2)                      # 粘贴
        self.assertEqual(self.text.get("1.0", "end-1c"), "粘贴进来的")

        self.text.delete("1.0", "end")
        self.text.insert("1.0", "abcdef")
        self.text.tag_add("sel", "1.0", "1.3")
        self.menu._invoke(0)                      # 剪切
        self.assertEqual(self.text.get("1.0", "end-1c"), "def")
        self.root.update()
        self.assertEqual(self.text.clipboard_get(), "abc")


@unittest.skipIf(tk is None, '当前 Python 未安装 tkinter')
class InputWiringTests(unittest.TestCase):
    """确认输入栏真的挂上了菜单，防止以后被顺手删掉。"""

    def test_input_has_edit_menu(self):
        try:
            probe = tk.Tk()
            probe.withdraw()
            probe.destroy()
        except tk.TclError as exc:
            self.skipTest(f'当前环境没有可用图形显示：{exc}')
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"REVIEWAGENT_HOME": tmp}), \
                patch.object(desktop.App, "load_sessions"), \
                patch.object(desktop.App, "show_welcome"):
            app = desktop.App()
            app.withdraw()
            try:
                for job in app.tk.call("after", "info"):
                    app.after_cancel(job)
                self.assertIsInstance(app.input_menu, edit_menu.EditMenu)
                self.assertIs(app.input_menu.widget, app.input)
                self.assertIsInstance(app.input, tk.Text)
            finally:
                app.destroy()
