"""模型设置对话框：读写与终端版共用的 ai_config.json。

模型清单来自终端同一份 CATALOG（`scripts/model_catalog.py`），这里不另写列表：
    scripts.model_catalog.catalog_payload()  →  下拉框选项
    scripts.model_choices.build_choices()    →  该选哪一个、切厂商怎么联动

读不到清单（脚本目录缺失、CATALOG 为空）时降级成手填「模型 ID」，
provider 与其它键一律不动。
"""
from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk

from .. import ROOT, config, theme
from ..widgets import FlatButton
from .base import Feature

CUSTOM_FALLBACK_TITLE = '自定义模型…'


class GatewayKey:
    """A key stays with the provider and endpoint it was entered for."""
    def __init__(self, provider: str, base_url: str, key: str):
        self.original = self.identity(provider, base_url)
        self.current = self.original
        self.saved_key = key

    @staticmethod
    def identity(provider: str, base_url: str) -> tuple[str, str]:
        return provider.strip().lower(), base_url.strip().rstrip('/')

    def update(self, provider: str, base_url: str, key: str) -> str:
        target = self.identity(provider, base_url)
        if target != self.current:
            self.current = target
            return self.saved_key if target == self.original else ''
        return key

    @property
    def changed(self) -> bool:
        return self.current != self.original


def _load_choices(provider: str, model: str):
    """返回 (choices, 错误信息)。任何异常都不抛给界面。"""
    try:
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        from scripts.model_choices import build_choices
    except Exception as exc:                            # noqa: BLE001
        return _degraded(provider, model), f'找不到模型清单模块（{exc}）'

    try:
        from scripts.model_catalog import active_model, catalog_payload

        payload = catalog_payload(active_model(config.CONFIG_PATH))
        choices = build_choices(payload.get('catalog') or (), provider, model)
    except Exception as exc:                            # noqa: BLE001
        return build_choices([], provider, model), str(exc)
    if not choices.get('options'):
        return choices, '模型清单为空'
    return choices, ''


def _degraded(provider: str, model: str) -> dict:
    return {'options': [], 'index': -1, 'models': [], 'model_index': 0,
            'custom': model, 'custom_enabled': True, 'base_url': '',
            'provider': provider, 'model': model, 'degraded': True,
            'custom_title': CUSTOM_FALLBACK_TITLE}


def open_settings(app) -> None:
    cfg = config.load_config()
    provider0 = str(cfg.get('provider') or '')
    model0 = str(cfg.get('model') or '')

    win = tk.Toplevel(app.root)
    win.title('模型设置')
    win.configure(bg=theme.BG)
    win.transient(app.root)
    win.grab_set()
    win.resizable(False, False)

    body = tk.Frame(win, bg=theme.BG, padx=24, pady=20)
    body.pack(fill='both', expand=True)
    body.grid_columnconfigure(1, weight=1)

    choices, load_error = _load_choices(provider0, model0)
    state = {
        'choices': choices,
    }
    key_binding = GatewayKey(provider0 or 'deepseek', str(cfg.get('base_url') or ''),
                             str(cfg.get('api_key') or ''))
    base_var = tk.StringVar(value=str(cfg.get('base_url') or ''))
    custom_title = choices.get('custom_title') or CUSTOM_FALLBACK_TITLE

    # Windows 默认的 vista 主题会忽略 Combobox 的 fieldbackground/foreground，
    # 结果就是白底 + 系统浅灰字，深色界面下几乎看不清。clam 主题才吃这些配置。
    # theme_use 是全局的，这里对 Scrollbar 一并补色，避免主窗口滚动条变回浅色。
    style = ttk.Style(win)
    try:
        style.theme_use('clam')
    except tk.TclError:
        pass                                        # 没有 clam 就沿用系统主题，不影响功能
    style.configure('Ra.TCombobox', fieldbackground=theme.PANEL,
                    background=theme.PANEL, foreground=theme.FG,
                    arrowcolor=theme.FG_DIM, selectbackground=theme.PANEL,
                    selectforeground=theme.FG, bordercolor=theme.BORDER,
                    lightcolor=theme.PANEL, darkcolor=theme.PANEL,
                    padding=4)
    style.map('Ra.TCombobox',
              fieldbackground=[('readonly', theme.PANEL), ('disabled', theme.BG)],
              foreground=[('readonly', theme.FG), ('disabled', theme.FG_FAINT)],
              selectbackground=[('readonly', theme.PANEL)],
              selectforeground=[('readonly', theme.FG)])
    style.configure('TScrollbar', background=theme.PANEL_HI,
                    troughcolor=theme.BG, bordercolor=theme.BORDER,
                    arrowcolor=theme.FG_DIM)
    # 下拉弹层是原生 Listbox，样式只能用 option 数据库
    win.option_add('*TCombobox*Listbox.background', theme.PANEL_HI)
    win.option_add('*TCombobox*Listbox.foreground', theme.FG)
    win.option_add('*TCombobox*Listbox.selectBackground', theme.ACCENT_DIM)
    win.option_add('*TCombobox*Listbox.selectForeground', theme.BG)
    win.option_add('*TCombobox*Listbox.font', theme.ui_font(11))

    def row_label(row: int, text: str) -> None:
        tk.Label(body, text=text, bg=theme.BG, fg=theme.FG_DIM,
                 font=theme.ui_font(11), anchor='w').grid(
            row=row, column=0, sticky='w', pady=8)

    def make_entry(row: int, value: str, show: str = '') -> tk.Entry:
        widget = tk.Entry(
            body, bg=theme.PANEL, fg=theme.FG, insertbackground=theme.FG,
            relief='flat', font=theme.ui_font(11), highlightthickness=1,
            highlightbackground=theme.BORDER, highlightcolor=theme.ACCENT_DIM,
            show=show,
        )
        widget.insert(0, value)
        widget.grid(row=row, column=1, sticky='ew', padx=(16, 0), ipady=6)
        return widget

    def make_combo(row: int) -> ttk.Combobox:
        widget = ttk.Combobox(body, state='readonly', style='Ra.TCombobox',
                              font=theme.ui_font(11), values=[])
        widget.grid(row=row, column=1, sticky='ew', padx=(16, 0), ipady=4)
        return widget

    # wraplength 要略小于输入框宽度：设太小会带出「API / Key」这种断词，
    # 而且提示文字一变长窗口就跟着变宽、控件跟着跳。
    hint = tk.Label(body, text='', bg=theme.BG, fg=theme.FG_FAINT,
                    font=theme.ui_font(10), anchor='w', justify='left',
                    wraplength=460)

    if choices.get('options'):
        row_label(0, '服务商')
        provider_cb = make_combo(0)
        provider_cb.configure(values=[opt['title'] for opt in choices['options']])
        provider_cb.current(choices['index'])

        row_label(1, '模型')
        model_cb = make_combo(1)

        # 自定义框始终可编辑：用户可以直接在这里打字，不需要先选「自定义模型…」。
        # 用 StringVar + trace 而不是按键事件 —— 粘贴、拖放、输入法都能覆盖到。
        custom_var = tk.StringVar(value=choices['custom'])
        row_label(2, '自定义模型')
        custom_entry = tk.Entry(
            body, textvariable=custom_var, bg=theme.PANEL, fg=theme.FG,
            insertbackground=theme.FG, relief='flat', font=theme.ui_font(11),
            highlightthickness=1, highlightbackground=theme.BORDER,
            highlightcolor=theme.ACCENT_DIM,
        )
        custom_entry.grid(row=2, column=1, sticky='ew', padx=(16, 0), ipady=6)

        row_label(3, 'API 地址')
        base_entry = make_entry(3, str(cfg.get('base_url') or ''))
        base_entry.configure(textvariable=base_var)

        syncing = {'on': False}

        def set_custom_text(text: str) -> None:
            """程序写文本框：带守卫，避免触发 trace 把下拉也切走。"""
            syncing['on'] = True
            custom_var.set(text)
            syncing['on'] = False

        def refresh_models() -> None:
            current = state['choices']
            values = list(current['models'])
            model_cb.configure(values=values + [custom_title])
            model_cb.current(current['model_index'])
            set_custom_text(current['custom'])

        def on_provider(_event=None) -> None:
            from scripts.model_choices import select_provider

            state['choices'] = select_provider(state['choices'], provider_cb.current())
            refresh_models()
            # 切厂商自动带出该厂商 base_url，用户之后仍可改
            option = state['choices']['options'][state['choices']['index']]
            base_var.set(str(cfg.get('base_url') or '') if option['keep']
                         else state['choices']['base_url'])
            sync_key()

        def on_model(_event=None) -> None:
            from scripts.model_choices import select_model

            state['choices'] = select_model(state['choices'], model_cb.current())
            if model_cb.current() < len(state['choices']['models']):
                # 选回清单里的模型 → 清掉手填内容，避免残留值让人误会
                set_custom_text('')
            else:
                custom_entry.focus_set()

        def on_custom_changed(*_args) -> None:
            """在手填框里输入（含粘贴）→ 模型下拉自动跳到「自定义模型…」。"""
            if syncing['on']:
                return
            if not custom_var.get().strip():
                return
            from scripts.model_choices import select_model

            custom_index = len(state['choices']['models'])
            if model_cb.current() != custom_index:
                model_cb.current(custom_index)
                state['choices'] = select_model(state['choices'], custom_index)

        # 变量跟着窗口一起回收，不需要手动摘 trace
        custom_var.trace_add('write', on_custom_changed)

        provider_cb.bind('<<ComboboxSelected>>', on_provider)
        model_cb.bind('<<ComboboxSelected>>', on_model)
        refresh_models()
        # 手动换行，不让 tk 自己在「12」和「个厂商」之间断
        list_hint_text = (f'模型清单来自终端：{len(choices["options"])} 个厂商\n'
                          f'清单里没有的模型，直接写在「自定义模型」里')
        hint.configure(text=list_hint_text, fg=theme.FG_FAINT)
        degrade = False
        last_row = 5
    else:
        # 读不到清单 → 手填模型 ID；provider 保持原值
        row_label(0, '模型 ID')
        custom_entry = make_entry(0, model0)
        provider_cb = model_cb = None
        row_label(1, 'API 地址')
        base_entry = make_entry(1, str(cfg.get('base_url') or ''))
        base_entry.configure(textvariable=base_var)
        hint.configure(text=f'无法读取模型清单：{load_error}\n已改为手动输入，保存不会改动其它配置。',
                       fg=theme.DANGER)
        degrade = True
        last_row = 3

    row_label(last_row - 1, 'API Key')
    key_entry = make_entry(last_row - 1, str(cfg.get('api_key') or ''), show='*')
    hint.grid(row=last_row, column=0, columnspan=2, sticky='ew', pady=(10, 0))

    def sync_key(*_args) -> None:
        provider = provider0 or 'deepseek'
        if not degrade:
            option = state['choices']['options'][state['choices']['index']]
            provider = option['file_provider'] or provider
        key = key_binding.update(provider, base_var.get(), key_entry.get())
        if key != key_entry.get():
            key_entry.delete(0, 'end')
            key_entry.insert(0, key)
        if key_binding.changed:
            hint.configure(text='服务商或 API 地址已变更\n请填写该地址对应的 API Key。',
                           fg=theme.DANGER)
        elif not degrade:
            hint.configure(text=list_hint_text, fg=theme.FG_FAINT)

    base_var.trace_add('write', sync_key)

    def save() -> None:
        sync_key()
        if degrade:
            model = custom_entry.get().strip()
            picked = (provider0, model) if model else None
        else:
            from scripts.model_choices import resolve

            # prefer_custom：手填框有内容就以它为准（不必先选「自定义模型…」）
            picked = resolve(state['choices'], model_cb.current(), custom_entry.get(),
                             prefer_custom=True)
        if not picked or not picked[1]:
            hint.configure(text='模型不能为空\n'
                                '请在下拉里选一个，或选「自定义模型…」后填写名称。',
                           fg=theme.DANGER)
            custom_entry.focus_set()
            return
        provider, model = picked
        key = key_entry.get().strip()
        # 换了厂商却没填新密钥 → 写进去的是别家的 key，调用必然 401。
        # 与其让用户拿到看不懂的报错，不如在这里拦住。
        if key_binding.changed and not key:
            hint.configure(text='还没填新服务商或地址的 API Key\n'
                                '请填写后再保存。',
                           fg=theme.DANGER)
            key_entry.focus_set()
            return
        data = dict(cfg)                                 # 保留 api_key / label 等其它键
        if not degrade:
            data['provider'] = provider                  # 降级模式不动 provider
            # label 只是给人看的注释，同步一下，免得配置里留着上一个厂商的名字
            idx = state['choices'].get('index', -1)
            options = state['choices'].get('options') or []
            if 0 <= idx < len(options):
                data['label'] = options[idx].get('label') or provider
        data['model'] = model
        data['base_url'] = base_entry.get().strip()
        if key:
            data['api_key'] = key
        try:
            config.save_config(data)
        except Exception as exc:                         # noqa: BLE001
            hint.configure(text=f'保存失败：{exc}', fg=theme.DANGER)
            return
        app.append(f'\n配置已保存 → {config.CONFIG_PATH}\n', 'accent')
        win.destroy()

    buttons = tk.Frame(body, bg=theme.BG)
    buttons.grid(row=last_row + 1, column=0, columnspan=2, sticky='e', pady=(16, 0))
    FlatButton(buttons, '保存', save, accent=True,
               font=theme.ui_font(11)).pack(side='left')
    FlatButton(buttons, '取消', win.destroy,
               font=theme.ui_font(11)).pack(side='left', padx=(8, 0))

    tk.Label(body, text=config.CONFIG_PATH, bg=theme.BG, fg=theme.FG_FAINT,
             font=theme.ui_font(8), anchor='w').grid(
        row=last_row + 2, column=0, columnspan=2, sticky='w', pady=(12, 0))

    # 焦点给「马上要操作的控件」，而不是密钥框：密钥多数情况不用改，
    # 打开就停在密钥上会让人以为必须填。
    if not degrade and provider_cb is not None:
        provider_cb.focus_set()
    else:
        custom_entry.focus_set()
    win.update_idletasks()
    x = app.root.winfo_rootx() + (app.root.winfo_width() - win.winfo_width()) // 2
    y = app.root.winfo_rooty() + (app.root.winfo_height() - win.winfo_height()) // 3
    win.geometry(f'+{max(0, x)}+{max(0, y)}')


FEATURES = [
    Feature(
        id='settings.model', group='系统', label='模型设置',
        handler=open_settings, order=10, shortcut='<Control-comma>', placement='toolbar',
        hint='下拉选择服务商与模型 / 改 API Key（与终端版共用配置）',
    ),
]
