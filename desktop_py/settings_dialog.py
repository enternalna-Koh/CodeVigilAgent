# -*- coding: utf-8 -*-
"""模型设置弹窗：应用内自选服务商 / 模型 / API 地址 / API Key。

与终端版共用同一份 ai_config.json（优先级也一致），所以这里改完终端也生效。
模型清单不另写列表，直接复用终端那份：
    scripts.model_catalog.catalog_payload()  → 下拉选项
    scripts.model_choices.build_choices()    → 选哪个、切厂商怎么联动
读不到清单（缺模块 / 清单为空）时降级为手填「模型 ID」，保存不动 provider。

API Key 只以 * 掩码回填，不写日志、不回显到消息区。
"""
from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

# 与 app.py 共用同一套配色/字体/圆角按钮。app.py 是同级模块。
from ui_kit import BG, BORDER, BTN_HOVER, FAIL_INK, FAINT, INK, MINT, PANEL, PANEL_HI, SUB
from ui_kit import RoundButton, ui_font

CUSTOM_FALLBACK_TITLE = "自定义模型…"


def _scripts_import(name: str):
    """延迟导入 scripts.*（ROOT 不在 sys.path 时补上）。失败抛异常由调用方降级。"""
    from ui_kit import ROOT

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import importlib
    return importlib.import_module(name)


def load_ai_config():
    """读 ai_config.json，优先级与终端版一致（REVIEWAGENT_CONFIG → home → project）。"""
    path = Path.home() / ".reviewagent" / "ai_config.json"
    try:
        path = Path(_scripts_import("scripts.agent_home").resolve_existing_config())
    except Exception:                                    # noqa: BLE001
        pass
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:                                    # noqa: BLE001
        data = {}
    return (data if isinstance(data, dict) else {}), path


def load_model_choices(provider: str, model: str, config_path):
    """返回 (choices, 错误信息)。清单来自终端同一份 CATALOG，不另写列表。"""
    degraded = {"options": [], "index": -1, "models": [], "model_index": 0,
                "custom": model, "custom_enabled": True, "base_url": "",
                "provider": provider, "model": model, "degraded": True,
                "custom_title": CUSTOM_FALLBACK_TITLE}
    try:
        catalog = _scripts_import("scripts.model_catalog")
        choices_mod = _scripts_import("scripts.model_choices")
        payload = catalog.catalog_payload(catalog.active_model(str(config_path)))
        choices = choices_mod.build_choices(payload.get("catalog") or (), provider, model)
    except Exception as exc:                             # noqa: BLE001
        return degraded, f"读不到模型清单（{exc}）"
    if not choices.get("options"):
        return degraded, "模型清单为空"
    return choices, ""


def save_ai_config(data: dict, path) -> None:
    """写回配置（0o600，与终端版 write_config 同一实现）。"""
    _scripts_import("scripts.agent_home").write_config(data, str(path))


class SettingsDialog(tk.Toplevel):
    """模型设置弹窗（模态）。"""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("模型设置")
        self.configure(bg=BG)
        self.transient(app)
        self.grab_set()
        self.resizable(False, False)

        cfg, self.cfg_path = load_ai_config()
        self.cfg = cfg
        provider0 = str(cfg.get("provider") or "")
        model0 = str(cfg.get("model") or "")

        body = tk.Frame(self, bg=BG, padx=22, pady=18)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(1, weight=1)
        self._body = body

        self.choices, load_error = load_model_choices(provider0, model0, self.cfg_path)
        self.degraded = not self.choices.get("options")
        self.base_var = tk.StringVar(value=str(cfg.get("base_url") or ""))
        self.custom_var = tk.StringVar(value=self.choices.get("custom") or model0)
        self._syncing = False
        self._key_scope = self._scope(provider0 or "deepseek",
                                      str(cfg.get("base_url") or ""))
        self._saved_key = str(cfg.get("api_key") or "")

        self._style_combo()

        hint = tk.Label(body, text="", bg=BG, fg=FAINT, font=ui_font(9),
                        anchor="w", justify="left", wraplength=430)
        self.hint = hint

        if self.degraded:
            self._build_degraded(model0)
            last = 3
            hint.configure(text=f"无法读取模型清单：{load_error}\n"
                                "已改为手动输入，保存不会改动其它配置。", fg=FAIL_INK)
        else:
            self._build_catalog(provider0)
            last = 5
            self.list_hint = (f"模型清单来自终端：{len(self.choices['options'])} 个厂商\n"
                              "清单里没有的模型，直接写在「自定义模型」里")
            hint.configure(text=self.list_hint, fg=FAINT)

        tk.Label(body, text="API Key", bg=BG, fg=SUB, font=ui_font(10),
                 anchor="w").grid(row=last - 1, column=0, sticky="w", pady=8)
        self.key_entry = self._entry(last - 1, self._saved_key, show="*")
        hint.grid(row=last, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        buttons = tk.Frame(body, bg=BG)
        buttons.grid(row=last + 1, column=0, columnspan=2, sticky="e", pady=(14, 0))
        RoundButton(buttons, "保存", self.save, font_size=11).pack(side="left")
        RoundButton(buttons, "取消", self.destroy, font_size=11).pack(
            side="left", padx=(8, 0))

        tk.Label(body, text=str(self.cfg_path), bg=BG, fg=FAINT,
                 font=ui_font(8), anchor="w").grid(
                     row=last + 2, column=0, columnspan=2, sticky="w", pady=(10, 0))

        self.bind("<Escape>", lambda _e: self.destroy())
        self._center()

    # ------------------------------------------------------------ 构造
    def _style_combo(self):
        # Windows 默认 vista 主题忽略 Combobox 配色，clam 才吃这些设置。
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Cv.TCombobox", fieldbackground=PANEL, background=PANEL,
                        foreground=INK, arrowcolor=SUB, selectbackground=PANEL,
                        selectforeground=INK, bordercolor=BORDER,
                        lightcolor=PANEL, darkcolor=PANEL, padding=4)
        style.map("Cv.TCombobox",
                  fieldbackground=[("readonly", PANEL), ("disabled", BG)],
                  foreground=[("readonly", INK), ("disabled", FAINT)],
                  selectbackground=[("readonly", PANEL)],
                  selectforeground=[("readonly", INK)])
        self.option_add("*TCombobox*Listbox.background", PANEL_HI)
        self.option_add("*TCombobox*Listbox.foreground", INK)
        self.option_add("*TCombobox*Listbox.selectBackground", BTN_HOVER)
        self.option_add("*TCombobox*Listbox.selectForeground", MINT)

    def _row_label(self, row: int, text: str) -> None:
        tk.Label(self._body, text=text, bg=BG, fg=SUB, font=ui_font(10),
                 anchor="w").grid(row=row, column=0, sticky="w", pady=8)

    def _entry(self, row: int, value: str, show: str = "") -> tk.Entry:
        widget = tk.Entry(self._body, bg=PANEL, fg=INK, insertbackground=INK,
                          relief="flat", font=ui_font(10), highlightthickness=1,
                          highlightbackground=BORDER, highlightcolor=MINT, show=show)
        widget.insert(0, value)
        widget.grid(row=row, column=1, sticky="ew", padx=(16, 0), ipady=6)
        return widget

    def _combo(self, row: int) -> ttk.Combobox:
        widget = ttk.Combobox(self._body, state="readonly", style="Cv.TCombobox",
                              font=ui_font(10), values=[])
        widget.grid(row=row, column=1, sticky="ew", padx=(16, 0), ipady=4)
        return widget

    def _build_catalog(self, provider0: str) -> None:
        self._row_label(0, "服务商")
        self.provider_cb = self._combo(0)
        self.provider_cb.configure(
            values=[opt["title"] for opt in self.choices["options"]])
        self.provider_cb.current(max(0, self.choices["index"]))

        self._row_label(1, "模型")
        self.model_cb = self._combo(1)

        self._row_label(2, "自定义模型")
        self.custom_entry = tk.Entry(
            self._body, textvariable=self.custom_var, bg=PANEL, fg=INK,
            insertbackground=INK, relief="flat", font=ui_font(10),
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=MINT)
        self.custom_entry.grid(row=2, column=1, sticky="ew", padx=(16, 0), ipady=6)

        self._row_label(3, "API 地址")
        self.base_entry = self._entry(3, str(self.cfg.get("base_url") or ""))
        self.base_entry.configure(textvariable=self.base_var)

        self.provider_cb.bind("<<ComboboxSelected>>", self._on_provider)
        self.model_cb.bind("<<ComboboxSelected>>", self._on_model)
        self.custom_var.trace_add("write", self._on_custom)
        self.base_var.trace_add("write", self._sync_key)
        self._refresh_models()

    def _build_degraded(self, model0: str) -> None:
        self.provider_cb = self.model_cb = None
        self._row_label(0, "模型 ID")
        self.custom_entry = self._entry(0, model0)
        self._row_label(1, "API 地址")
        self.base_entry = self._entry(1, str(self.cfg.get("base_url") or ""))
        self.base_entry.configure(textvariable=self.base_var)
        self.base_var.trace_add("write", self._sync_key)

    # ------------------------------------------------------------ 联动
    @staticmethod
    def _scope(provider: str, base_url: str):
        return provider.strip().lower(), base_url.strip().rstrip("/")

    def _set_custom_text(self, text: str) -> None:
        self._syncing = True
        self.custom_var.set(text)
        self._syncing = False

    def _refresh_models(self) -> None:
        current = self.choices
        values = list(current["models"])
        self.model_cb.configure(values=values + [current.get("custom_title")
                                                 or CUSTOM_FALLBACK_TITLE])
        self.model_cb.current(max(0, current["model_index"]))
        self._set_custom_text(current["custom"])

    def _on_provider(self, _event=None) -> None:
        from scripts.model_choices import select_provider

        self.choices = select_provider(self.choices, self.provider_cb.current())
        self._refresh_models()
        option = self.choices["options"][self.choices["index"]]
        self.base_var.set(str(self.cfg.get("base_url") or "") if option["keep"]
                          else self.choices["base_url"])
        self._sync_key()

    def _on_model(self, _event=None) -> None:
        from scripts.model_choices import select_model

        self.choices = select_model(self.choices, self.model_cb.current())
        if self.model_cb.current() < len(self.choices["models"]):
            self._set_custom_text("")
        else:
            self.custom_entry.focus_set()

    def _on_custom(self, *_args) -> None:
        """手填（含粘贴）→ 下拉自动跳到「自定义模型…」。"""
        if self._syncing or not self.custom_var.get().strip() or self.degraded:
            return
        from scripts.model_choices import select_model

        custom_index = len(self.choices["models"])
        if self.model_cb.current() != custom_index:
            self.model_cb.current(custom_index)
            self.choices = select_model(self.choices, custom_index)

    def _sync_key(self, *_args) -> None:
        """换服务商/地址时密钥跟着作用域走，避免拿别家的 key 去调用（必然 401）。"""
        provider = str(self.cfg.get("provider") or "deepseek")
        if not self.degraded:
            option = self.choices["options"][self.choices["index"]]
            provider = option["file_provider"] or provider
        scope = self._scope(provider, self.base_var.get())
        if scope != self._key_scope:
            self._key_scope = scope
            keep = self._saved_key
            self.key_entry.delete(0, "end")
            self.key_entry.insert(0, keep)
            self.hint.configure(text="服务商或 API 地址已变更\n"
                                     "请填写该地址对应的 API Key。", fg=FAIL_INK)
        elif not self.degraded:
            self.hint.configure(text=self.list_hint, fg=FAINT)

    # ------------------------------------------------------------ 保存
    def save(self) -> None:
        self._sync_key()
        if self.degraded:
            model = self.custom_entry.get().strip()
            picked = (str(self.cfg.get("provider") or ""), model) if model else None
        else:
            from scripts.model_choices import resolve

            picked = resolve(self.choices, self.model_cb.current(),
                             self.custom_entry.get(), prefer_custom=True)
        if not picked or not picked[1]:
            self.hint.configure(text="模型不能为空\n"
                                     "请在下拉里选一个，或选「自定义模型…」后填写名称。",
                                fg=FAIL_INK)
            self.custom_entry.focus_set()
            return

        provider, model = picked
        key = self.key_entry.get().strip()
        if self._key_scope != self._scope(str(self.cfg.get("provider") or "deepseek"),
                                         str(self.cfg.get("base_url") or "")) and not key:
            self.hint.configure(text="还没填新服务商或地址的 API Key\n请填写后再保存。",
                                fg=FAIL_INK)
            self.key_entry.focus_set()
            return

        data = dict(self.cfg)                            # 保留 api_key / label 等其它键
        if not self.degraded:
            data["provider"] = provider
            idx = self.choices.get("index", -1)
            options = self.choices.get("options") or []
            if 0 <= idx < len(options):
                data["label"] = options[idx].get("label") or provider
        data["model"] = model
        data["base_url"] = self.base_entry.get().strip()
        if key:
            data["api_key"] = key
        try:
            save_ai_config(data, self.cfg_path)
        except Exception as exc:                         # noqa: BLE001
            self.hint.configure(text=f"保存失败：{exc}", fg=FAIL_INK)
            return

        self.app.set_status(f"已保存模型配置：{model}（{self.cfg_path}）")
        self.destroy()

    def _center(self) -> None:
        self.update_idletasks()
        app = self.app
        x = app.winfo_rootx() + (app.winfo_width() - self.winfo_width()) // 2
        y = app.winfo_rooty() + (app.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
