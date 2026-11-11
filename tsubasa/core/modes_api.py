"""Streaming endpoints for the two modes that don't go through the chat model's tool loop.

/api/terminal-ai  Terminal mode: Sensei's library, router and writer, checker, Run tickets and live output.
/api/images-create  Images mode: the message is the prompt; RealVisXL makes the picture directly (no chat model).
Both stream server-sent events in the same format as /api/chat and save the turn in the chat like any other answer.
"""
import json
import re
import secrets
import threading
import time

from core.config import IMAGE_MODEL
from core.platform import WINDOWS, is_admin
from core.images import validate as validate_image

IMAGE_TAG = "[[image:{id}:{workspace}]]"


def _chat(app, cid):
    if not isinstance(cid, str) or not re.fullmatch("[a-f0-9]{32}", cid):
        raise ValueError("Start a chat first.")
    with app.store.connect() as db:
        if not db.execute("SELECT id FROM chats WHERE id=?", (cid,)).fetchone():
            raise ValueError("Chat not found.")


def _history(app, cid):
    """The last finished request/command pairs of this chat, for follow-ups such as "now only the big ones"."""
    with app.store.connect() as db:
        rows = db.execute("SELECT role,content,state FROM messages WHERE chat=? ORDER BY id DESC LIMIT 6", (cid,)).fetchall()
    pairs = []
    for a, u in zip(rows[::2], rows[1::2]):
        if a["role"] == "assistant" and u["role"] == "user" and a["state"] == "complete":
            pairs.append({"q": u["content"], "a": a["content"][:1500]})
    return list(reversed(pairs))


class Stream:
    """Server-sent events on the handler, plus the request id that /api/cancel and Stop use."""

    def __init__(self, handler):
        self.h, self.app = handler, handler.app
        self.id, self.cancelled, self.closed = secrets.token_hex(12), threading.Event(), False

    def __enter__(self):
        with self.app.active_lock:
            self.app.active[self.id] = self.cancelled
        self.h.send_response(200)
        self.h.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.h.send_header("Connection", "close")
        self.h.end_headers()
        self.emit("start", {"request_id": self.id})
        return self

    def __exit__(self, *exc):
        with self.app.active_lock:
            self.app.active.pop(self.id, None)
        self.h.close_connection = True

    def emit(self, kind, data):
        if self.closed:
            return
        try:
            self.h.wfile.write(("data: " + json.dumps({"type": kind, "data": data}) + "\n\n").encode())
            self.h.wfile.flush()
        except OSError:
            self.closed = True
            self.cancelled.set()


def _locked(handler):
    if not handler.app.operation.acquire(False):
        handler.reply(409, {"error": "Wait for the current request to finish."})
        return False
    return True


# ---------------------------------------------------------------------------------------------- terminal
def stored_answer(ans):
    return f"```{'powershell' if WINDOWS else 'zsh'}\n{ans['code']}\n```\n{ans['text']}".strip() if ans.get("code") else (ans.get("text") or "")


def terminal(handler, body):
    app, sensei = handler.app, handler.app.sensei
    action = body.get("action")
    if action == "warm":
        sensei.shell.warm_up()
        return handler.reply(200, {"ok": True, "model": sensei.model})
    if action == "stop":
        sensei.shell.stop()
        return handler.reply(200, {"ok": True})
    if action == "cwd":
        return handler.reply(200, {"cwd": sensei.shell.session.cwd})
    if action == "cd":
        # Code mode's project folder: the terminal session moves there (any non-system folder).
        from core.pc_files import resolve
        try:
            folder = resolve(body.get("path"))
            if not folder.is_dir():
                raise ValueError("That folder does not exist.")
        except ValueError as exc:
            return handler.reply(400, {"error": str(exc)})
        if not _locked(handler):
            return
        try:
            shell = sensei.shell
            if shell.session.alive:
                q = "'" + str(folder).replace("'", "''" if WINDOWS else "'\\''") + "'"
                for _ in shell.run(f"Set-Location -LiteralPath {q}" if WINDOWS else f"cd {q}"):
                    pass
            shell.session.cwd = str(folder)
        finally:
            app.operation.release()
        return handler.reply(200, {"cwd": str(folder)})
    if action == "check":
        code = body.get("code")
        if not isinstance(code, str) or not 1 <= len(code) <= 4000:
            return handler.reply(400, {"error": "Enter a command of 1-4,000 characters."})
        return handler.reply(200, sensei.check(code))
    if action == "open":
        code = body.get("code") or ""
        if not isinstance(code, str) or len(code) > 4000:
            return handler.reply(400, {"error": "Invalid command."})
        refused = sensei.tickets.gate(sensei.shell, code, body) if code.strip() else None
        if refused:
            return handler.reply(409, {"error": refused})
        sensei.shell.open_window(code)
        return handler.reply(200, {"ok": True})
    if action == "run":
        return run(handler, body)
    if action not in ("ask", "task"):
        return handler.reply(400, {"error": "Unknown terminal action."})
    q = body.get("q")
    try:
        if not isinstance(q, str) or not 1 <= len(q.strip()) <= 2000:
            raise ValueError("Describe the task in 1-2,000 characters.")
        _chat(app, body.get("chat_id"))
    except ValueError as exc:
        return handler.reply(400, {"error": str(exc)})
    if not _locked(handler):
        return
    cid, q = body["chat_id"], q.strip()
    saved = None
    try:
        with Stream(handler) as s:
            history = _history(app, cid)
            saved = app.store.begin(cid, q)
            if app.client.observed_model not in (None, sensei.model):
                s.emit("status", f"Loading {sensei.model} for the terminal (about 15 s once)…")
            try:
                events = [("answer", sensei.task(body.get("source"), q))] if action == "task" else sensei.ask(q, history, s.cancelled)
                for kind, value in events:
                    if s.cancelled.is_set():
                        break
                    s.emit(kind, value)
                    if kind == "answer":
                        app.store.finish(saved, stored_answer(value), "", "complete")
                        saved = None
            except (OSError, RuntimeError, ValueError) as exc:
                s.emit("error", str(exc) if isinstance(exc, ValueError) else
                       "The AI engine is not answering. Tested library commands still work: try simpler words, "
                       "e.g. “what is my IP address”.")
            s.emit("done", {"cancelled": s.cancelled.is_set(), "model": sensei.model})
    finally:
        if saved:
            app.store.finish(saved, "", "", "stopped")
        app.operation.release()


def run(handler, body):
    if WINDOWS:
        from core.sensei_term import fix_code   # the Sensei library loads on first terminal use, not at app start
    else:
        fix_code = lambda c: c   # noqa: E731
    app, sensei = handler.app, handler.app.sensei
    code = body.get("code")
    if not isinstance(code, str) or not 1 <= len(code) <= 4000:
        return handler.reply(400, {"error": "Invalid command."})
    if is_admin():
        return handler.reply(400, {"error": "Run Tsubasa without administrator rights."})
    refused = sensei.tickets.gate(sensei.shell, code, body)
    if refused:
        return handler.reply(409, {"error": refused})
    if not _locked(handler):
        return
    try:
        with Stream(handler) as s:
            s.emit("cwd", sensei.shell.session.cwd)
            batch, last = [], time.monotonic()
            for kind, data in sensei.shell.run(fix_code(code)):
                if kind == "done":
                    if batch:
                        s.emit("lines", batch)
                    s.emit("ran", data)
                    break
                batch.append([kind, data if isinstance(data, str) else str(data)])
                if len(batch) >= 200 or time.monotonic() - last > 0.05:
                    s.emit("lines", batch)
                    batch, last = [], time.monotonic()
                if s.cancelled.is_set():
                    sensei.shell.stop()
            s.emit("done", {"cancelled": s.cancelled.is_set()})
    finally:
        app.operation.release()


# ---------------------------------------------------------------------------------------------- images
def images(handler, body):
    app = handler.app
    prompt, size, w = body.get("prompt"), body.get("size", "1024x1024"), body.get("workspace", "default")
    try:
        _chat(app, body.get("chat_id"))
        validate_image({"prompt": prompt, "size": size})
        app.images.workspace(w)
    except (ValueError, TypeError) as exc:
        return handler.reply(400, {"error": str(exc)})
    if not _locked(handler):
        return
    saved = None
    try:
        with Stream(handler) as s:
            saved = app.store.begin(body["chat_id"], prompt.strip())
            try:
                if not app.images.online():
                    s.emit("status", f"Starting the image engine ({IMAGE_MODEL})…")
                    app.images.start_owned()
                result, error = {}, []
                def work():
                    try:
                        result.update(app.images.generate(w, {"prompt": prompt.strip(), "size": size}, s.cancelled))
                    except ValueError as exc:
                        error.append(str(exc))
                t0, worker = time.monotonic(), threading.Thread(target=work, daemon=True)
                worker.start()
                while worker.is_alive():
                    s.emit("progress", {"seconds": round(time.monotonic() - t0)})
                    worker.join(1)
                if error:
                    raise ValueError(error[0])
                app.images.touch()
                s.emit("image", result)
                app.store.finish(saved, f"{IMAGE_TAG.format(**result)}\n{IMAGE_MODEL} · {size.replace('x', '×')} · "
                                 f"{result['seconds']:.0f} s", "", "complete")
                saved = None
            except ValueError as exc:
                s.emit("error", str(exc))
            s.emit("done", {"cancelled": s.cancelled.is_set(), "model": IMAGE_MODEL})
    finally:
        if saved:
            app.store.finish(saved, "", "", "stopped")
        app.operation.release()


# ---------------------------------------------------------------------------------------------- agent (Code mode, PC files)
def agent(handler, body):
    """Code mode (terminal + files) or Chat with "Files on this PC": one approved step at a time."""
    app = handler.app
    message, model, code = body.get("message"), body.get("model"), body.get("code") is True
    try:
        if not isinstance(message, str) or not 1 <= len(message.strip()) <= 12000:
            raise ValueError("Enter a message of 1-12,000 characters.")
        _chat(app, body.get("chat_id"))
        app.client.require_model(model)
    except ValueError as exc:
        return handler.reply(400, {"error": str(exc)})
    if not _locked(handler):
        return
    cid, saved, parts, thinking = body["chat_id"], None, [], []
    try:
        with Stream(handler) as s:
            messages = app.store.context(cid, message.strip())
            extras = app.store.instructions(cid)   # Code mode swaps the system prompt but keeps these
            if body.get("library") is True:
                extra, used = app.library.context(message)
                messages[0]["content"] += extra
                extras += extra
                if used:
                    s.emit("library", used)
            saved = app.store.begin(cid, message.strip())
            try:
                options = {"think": bool(body.get("think"))} if not code else {}
                for kind, value in app.agent.stream(model, messages, code=code, turn=s.id, emit=s.emit,
                                                    cancelled=s.cancelled, options=options, extras=extras,
                                                    autorun=code and body.get("autorun") is True):
                    if kind == "text":
                        parts.append(value)
                        s.emit("text", value)
                    elif kind == "thinking":
                        thinking.append(value)
                        s.emit("thinking", value)
                    elif kind == "summary":
                        parts.append("\n\n**Steps**\n" + "\n".join(f"- {line}" for line in value))
                    elif kind == "usage":
                        s.emit("usage", value)
            except (OSError, RuntimeError, ValueError) as exc:
                s.emit("error", str(exc) if isinstance(exc, (ValueError, RuntimeError)) else
                       "Local AI connection failed. Check that the engine is running, then retry.")
            app.store.finish(saved, "".join(parts).strip(), "".join(thinking), "stopped" if s.cancelled.is_set() else "complete")
            saved = None
            s.emit("done", {"cancelled": s.cancelled.is_set(), "model": model})
    finally:
        if saved:
            app.store.finish(saved, "".join(parts).strip(), "", "stopped")
        app.operation.release()


def agent_decision(handler, body):
    action = body.get("action")
    if action not in ("allow", "skip", "stop"):
        return handler.reply(400, {"error": "Choose Allow, Skip or Stop."})
    # elevate: the user pressed "Run as administrator" on this step (Windows then shows its own prompt)
    answer = {"action": action, "confirmed": body.get("confirmed") is True, "elevate": body.get("elevate") is True}
    if isinstance(body.get("code"), str) and len(body["code"]) <= 4000:
        answer["code"] = body["code"]
    ok = handler.app.agent.approvals.decide(body.get("ticket"), body.get("request_id"), answer)
    return handler.reply(200 if ok else 409, {"ok": True} if ok else {"error": "This step already finished or expired."})


# ---------------------------------------------------------------------------------------------- library and pickers
def library(handler, body):
    lib, action = handler.app.library, body.get("action")
    try:
        if action == "list":
            return handler.reply(200, {"packs": lib.packs()})
        if action == "toggle":
            lib.toggle(body.get("id"), body.get("on") is True)
        elif action == "create":
            return handler.reply(200, {"id": lib.create(body.get("name"), body.get("description", ""),
                                                        body.get("instructions", ""), body.get("icon", "✦"))})
        elif action == "update":
            lib.update(body.get("id"), body.get("name"), body.get("description", ""), body.get("instructions", ""))
        elif action == "delete":
            lib.delete(body.get("id"))
        elif action == "add_source":
            return handler.reply(200, lib.add_source(body.get("id"), body.get("path")))
        elif action == "remove_source":
            lib.remove_source(int(body.get("source")))
        elif action == "refresh":
            lib.refresh(body.get("id"))
        else:
            raise ValueError("Unknown library action.")
        return handler.reply(200, {"ok": True})
    except (ValueError, TypeError) as exc:
        return handler.reply(400, {"error": str(exc)})


def pick(handler, body):
    from core.picker import pick as native_pick
    try:
        return handler.reply(200, native_pick(body.get("kind"), body.get("title", "")))
    except (ValueError, OSError) as exc:
        return handler.reply(400, {"error": str(exc)})
