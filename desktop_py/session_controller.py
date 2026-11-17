"""主线程会话选择、历史加载及提问/审查的上下文快照。"""
from __future__ import annotations

import json
from pathlib import Path
import time
import uuid
from tkinter import filedialog

from ui_kit import ROOT


def parse_json(text):
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if 0 <= start < end:
            try:
                return json.loads(text[start:end + 1])
            except ValueError:
                pass
    return None


def err_line(err, limit=120):
    lines = [line.strip() for line in (err or "").splitlines() if line.strip()]
    return lines[-1][:limit] if lines else ""


class SessionController:
    def _context_blocked(self):
        if self._running:
            self.set_status("任务运行中，先取消或等它结束再切换上下文")
            return True
        return False

    def _advance_conversation(self):
        self._conversation_epoch += 1
        self._pending_session = None
        return self._conversation_epoch

    def choose_repo(self):
        if self._context_blocked():
            return
        path = filedialog.askdirectory(title="选择 Git 仓库", initialdir=self.repo_var.get())
        if path:
            self.repo_var.set(str(Path(path).resolve()))
            self.new_conversation()

    def review_online(self):
        self._review(False)

    def review_offline(self):
        self._review(True)

    def _review(self, offline):
        if self._context_blocked():
            return
        if self._pending_session:
            self.set_status("正在读取会话，请稍后再审查")
            return
        repo = str(Path(self.repo_var.get().strip() or ROOT).resolve())
        epoch = self._conversation_epoch
        args = ["review"] + (["--offline"] if offline else [])
        label = "离线审查" if offline else "审查当前改动"

        def done(result):
            if epoch != self._conversation_epoch:
                return
            if result[0] == "error":
                self.set_status(f"{label}失败")
                return
            if self.cancel_flag:
                self.set_status("已取消")
                return
            code, out, err = result
            text = (out or err).strip() or f"{label}没有输出。"
            self.append_output(f"仓库：{repo}\n{text}")
            self.set_status(f"{label}完成（退出码 {code}）")

        self.run_async(lambda: self.run_cli(*args, timeout=180, cwd=repo), done, label,
                       cancellable=True)

    def send(self):
        text = self.input.get("1.0", "end").strip()
        if not text:
            return
        if self._context_blocked():
            return
        if self._pending_session:
            self.set_status("正在读取会话，请稍后发送；输入已保留")
            return
        self.input.delete("1.0", "end")
        self.cancel_flag = False
        client_start = time.perf_counter()
        self.append_user(text, "running")
        self.begin_chat_timing(client_start)
        if not self.session_name:
            self.session_name = "desktop-win-" + uuid.uuid4().hex
        session = self.session_name
        repo = str(Path(self.repo_var.get().strip() or ROOT).resolve())
        epoch = self._advance_conversation()
        # 发送立即废弃旧缓存，取消/失败也不能恢复旧的未追加历史。
        self._forget_session(session)

        def work():
            args = ["chat", "--message", text, "--network", "auto", "--json",
                    "--session", session, "--repository", repo]
            return self.run_cli(*args, timeout=180, cwd=repo,
                                extra_env={"REVIEWAGENT_CLIENT_START": f"{client_start:.6f}"})

        def done(result):
            if epoch != self._conversation_epoch:
                return
            seconds = self.stop_chat_timing()
            if result[0] == "error":
                self._mark_last_user("failed", str(result[1]), seconds)
                self.set_status("请求失败")
                return
            code, out, err = result
            parsed = parse_json(out)
            payload = parsed if isinstance(parsed, dict) else {}
            if seconds is None:
                elapsed = payload.get("elapsed_ms")
                if isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool) and elapsed >= 0:
                    seconds = elapsed / 1000
            if self.cancel_flag:
                self._mark_last_user("interrupted", "", seconds)
                self.set_status("已取消")
                return
            reply = payload.get("reply")
            if payload.get("ok") and reply:
                elapsed_ms = payload.get("elapsed_ms")
                if isinstance(elapsed_ms, bool) or not isinstance(elapsed_ms, (int, float)):
                    elapsed_ms = int(round((seconds or 0) * 1000))
                self._settle_last_user()
                self.append_agent(str(reply), elapsed_ms=elapsed_ms,
                                  finished_at=payload.get("finished_at") or "")
                self.session_name = (payload.get("session") or payload.get("session_name") or session)
                self._forget_session(self.session_name)
                self.set_status("就绪")
                self.load_sessions()
            else:
                reason = payload.get("error") or err_line(err) or "未知错误"
                self._mark_last_user("failed", reason, seconds)
                self.set_status(err_line(err) if parsed is None and err_line(err) else "请求失败")

        self.run_async(work, done, "提问", cancellable=True)

    def new_conversation(self):
        if self._context_blocked():
            return
        self._advance_conversation()
        self.session_name = None
        self.clear_transcript()
        self._set_session_header("新对话", f"仓库：{self.repo_var.get()}")
        self.input.delete("1.0", "end")
        self.input.focus_set()
        self.set_status("新对话")
        self.render_sessions(self._sessions_cache)

    def _new_conversation_blocked(self):
        self.set_status("任务运行中，先取消或等它结束再开新对话")

    def load_sessions(self):
        epoch = self._conversation_epoch
        self._list_request = getattr(self, "_list_request", 0) + 1
        request = self._list_request
        pending = "读取会话列表 运行中…"

        def done(result):
            if epoch != self._conversation_epoch or request != self._list_request:
                return
            if result[0] == "error":
                if self.status_var.get() == pending:
                    self.set_status("会话列表读取失败")
                return
            code, out, err = result
            parsed = parse_json(out)
            payload = parsed if isinstance(parsed, dict) else {}
            self._sessions_cache = payload.get("sessions") or []
            self.render_sessions(self._sessions_cache)
            if self.status_var.get() == pending:
                self.set_status(err_line(err) if parsed is None and err_line(err) else "就绪")

        self.run_async(lambda: self.run_cli("sessions", "list", timeout=60, track=False),
                       done, "读取会话列表")

    def delete_session(self, name):
        if not name or self._context_blocked():
            return
        # 删除一开始就作废读取，不等 CLI 返回后才使在飞结果失效。
        self._advance_conversation()
        epoch = self._conversation_epoch
        self._forget_session(name)
        if self.session_name == name:
            self.session_name = None
            self.clear_transcript()
            self._set_session_header("新对话", f"仓库：{self.repo_var.get()}")
        self._sessions_cache = [s for s in self._sessions_cache if s.get("name") != name]
        self.render_sessions(self._sessions_cache)
        self._deleting_sessions = getattr(self, "_deleting_sessions", set())
        self._deleting_sessions.add(name)

        def done(result):
            self._deleting_sessions.discard(name)
            self._forget_session(name)
            if epoch != self._conversation_epoch:
                return
            if result[0] == "error":
                detail = str(result[1])
            else:
                code, out, err = result
                detail = err_line(err) or "未知错误" if code != 0 else ""
            self.load_sessions()
            self.set_status(f"删除失败：{detail}" if detail else f"已删除会话：{name}")

        self.run_async(lambda: self.run_cli("sessions", "delete", name, timeout=60,
                                            track=False), done, "删除会话")

    def show_session(self, name):
        if not name or self._context_blocked():
            return
        if name in getattr(self, "_deleting_sessions", set()):
            self.set_status("正在删除该会话，请稍后")
            return
        epoch = self._advance_conversation()
        cached = self._session_cache.get(name)
        if cached is not None:
            session, parsed, err = cached
            self._apply_session(name, session, parsed, err, from_cache=True)
            return
        self._pending_session = name
        self.session_name = None
        self.clear_transcript()
        self.render_sessions(self._sessions_cache)
        self.set_status(f"正在打开会话：{name}")

        def done(result):
            if epoch != self._conversation_epoch:
                return
            if result[0] == "error":
                self._pending_session = None
                self.render_sessions(self._sessions_cache)
                self.set_status("读取会话失败")
                return
            code, out, err = result
            parsed = parse_json(out)
            payload = parsed if isinstance(parsed, dict) else {}
            session = payload.get("session")
            if code != 0 or not isinstance(session, dict):
                self._pending_session = None
                self.render_sessions(self._sessions_cache)
                self.set_status("读取会话失败")
                return
            self._apply_session(name, session, parsed, err)

        self.run_async(lambda: self.run_cli("sessions", "show", name, timeout=60,
                                            track=False), done, "读取会话")

    def _apply_session(self, name, session, parsed=None, err="", from_cache=False):
        self._pending_session = None
        self._remember_session(name, session, parsed, err)
        messages = session.get("messages") or []
        self.session_name = name
        repository = session.get("repository")
        if repository:
            self.repo_var.set(repository)
        self._set_session_header(session.get("title") or name,
                                 f"仓库：{repository or self.repo_var.get()}")
        self.stop_chat_timing()
        self.messages = []
        for message in messages:
            role = message.get("role")
            content = message.get("content") or ""
            if role == "user":
                self.messages.append({"role": "user", "content": content,
                                      "status": message.get("status") or "",
                                      "detail": message.get("error") or "",
                                      "sent_at": message.get("started_at") or message.get("updated_at"),
                                      "elapsed_ms": message.get("elapsed_ms")})
            elif role == "assistant":
                self.messages.append({"role": "assistant", "content": content,
                                      "status": "completed",
                                      "elapsed_ms": message.get("elapsed_ms"),
                                      "finished_at": message.get("finished_at") or message.get("updated_at")})
        self.rerender()
        self._schedule_rewrap(60)
        self.render_sessions(self._sessions_cache)
        note = "（缓存）" if from_cache else ""
        self.set_status(err_line(err) if parsed is None and err_line(err)
                        else f"已打开会话：{name}{note}")

    def _remember_session(self, name, session, parsed, err):
        self._session_cache.pop(name, None)
        self._session_cache[name] = (session, parsed, err)
        while len(self._session_cache) > 6:
            self._session_cache.pop(next(iter(self._session_cache)), None)

    def _forget_session(self, name):
        self._session_cache.pop(name, None)
