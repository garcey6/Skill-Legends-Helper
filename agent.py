"""Floating in-game assistant: global hotkey -> screen capture -> RAG -> HUD.

Run with:
    python agent.py
    python agent.py --capture-key Alt+C --port 8777
"""
from __future__ import annotations

import argparse
import ctypes
import os
import queue
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# DPI awareness must be set before tkinter creates a window.
from app.overlay import capture  # noqa: E402

capture.enable_dpi_awareness()

from app.config import BASE_DIR  # noqa: E402
from app.kb.recommend import Advisor  # noqa: E402
from app.overlay.hotkey import MOD_ALT, MOD_CONTROL, MOD_NOREPEAT, MOD_SHIFT, MOD_WIN, HotkeyManager, parse_combo  # noqa: E402
from app.overlay.hud import Hud, render_error, render_loading, render_result  # noqa: E402
from app.vision.recognizer import Recognizer  # noqa: E402

CAPTURE_DIR = BASE_DIR / "data" / "captures"
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def acquire_single_instance():
    """Named mutex so a second double-click cannot steal the hotkeys."""
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, "Local\\XuanJiAssistantOverlay")
    if not handle:
        return None
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        return None
    return handle


class KeyWatcher:
    """Fallback for environments where WM_HOTKEY is swallowed.

    GetAsyncKeyState is global, so polling it still works while the game owns
    the foreground window.  The dispatcher below de-duplicates the two paths.
    """

    MODIFIER_VKS = {
        MOD_CONTROL: (0x11,),   # VK_CONTROL
        MOD_ALT: (0x12,),       # VK_MENU
        MOD_SHIFT: (0x10,),     # VK_SHIFT
        MOD_WIN: (0x5B, 0x5C),  # VK_LWIN / VK_RWIN
    }

    def __init__(self, combo: str) -> None:
        mods, vk = parse_combo(combo)
        self.vk = vk
        self.modifiers = []
        for bit, keys in self.MODIFIER_VKS.items():
            if mods & bit:
                self.modifiers.append(keys)
        self.down = False

    def pressed(self) -> bool:
        key_down = bool(user32.GetAsyncKeyState(self.vk) & 0x8000)
        mods_down = all(any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in keys) for keys in self.modifiers)
        edge = key_down and mods_down and not self.down
        self.down = key_down
        return edge


def choose_hotkeys(args) -> Dict[str, str]:
    """Pick the preferred keys, falling back when another app owns them.

    F8/F9 are common screenshot keys and are often already registered.  The
    fallback is selected by actually attempting RegisterHotKey, then releasing
    it; the real manager registers the chosen keys immediately afterwards.
    """
    preferred = {
        "capture": args.capture_key,
        "toggle": args.toggle_key,
        "quit": args.quit_key,
    }
    alternatives = {
        "capture": ["F6", "F10", "Ctrl+Shift+F8"],
        "toggle": ["F7", "F11", "Ctrl+Shift+F9"],
        "quit": ["Ctrl+Shift+Q", "Ctrl+Alt+W", "Ctrl+Shift+X"],
    }
    chosen: Dict[str, str] = {}
    used = set()
    for action in ("capture", "toggle", "quit"):
        for combo in [preferred[action]] + alternatives[action]:
            try:
                mods, vk = parse_combo(combo)
            except ValueError:
                continue
            if (mods, vk) in used:
                continue
            if user32.RegisterHotKey(None, 991, mods | MOD_NOREPEAT, vk):
                user32.UnregisterHotKey(None, 991)
                chosen[action] = combo
                used.add((mods, vk))
                break
        else:
            chosen[action] = preferred[action]
    return chosen


class Agent:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.hotkeys_cfg = choose_hotkeys(args)
        self.capture_key = self.hotkeys_cfg["capture"]
        self.toggle_key = self.hotkeys_cfg["toggle"]
        self.quit_key = self.hotkeys_cfg["quit"]
        self.hud = Hud(
            alpha=args.alpha,
            scale=(args.hud_scale or None),
            capture_key=self.capture_key,
            toggle_key=self.toggle_key,
            quit_key=self.quit_key,
        )
        self.recognizer = Recognizer()
        self.advisor = Advisor()
        self.events: "queue.Queue[str]" = queue.Queue()
        self.hotkeys = HotkeyManager(
            self.events,
            capture=self.capture_key,
            toggle=self.toggle_key,
            quit_combo=self.quit_key,
        )
        self.watchers = {
            "capture": KeyWatcher(self.capture_key),
            "toggle": KeyWatcher(self.toggle_key),
            "quit": KeyWatcher(self.quit_key),
        }
        self._last_dispatch: Dict[str, float] = {}
        self.server_url = "http://127.0.0.1:%d" % args.port
        self.httpd = None
        self.last_game_hwnd: Optional[int] = None
        self.busy = False
        self.running = True
        self._closed = False

    # ------------------------------------------------------------------ setup
    def start_server(self) -> None:
        if self.args.no_server:
            return
        try:
            from app import server as server_module
            from app.server import create_server

            server_module.OVERLAY_TRIGGER = lambda: self.events.put("capture")
            httpd, port = create_server(port=self.args.port)
            self.httpd = httpd
            self.server_url = "http://127.0.0.1:%d" % port
            try:
                (BASE_DIR / "data" / "server_url.txt").write_text(self.server_url, encoding="utf-8")
            except OSError:
                pass
            threading.Thread(target=httpd.serve_forever, daemon=True, name="control-panel").start()
            print("设置与攻略库：%s" % self.server_url, flush=True)
        except Exception as exc:
            print("网页控制台不可用：%s" % exc, flush=True)

    def run(self) -> None:
        self.hotkeys.start()
        for error in self.hotkeys.errors:
            print("热键提示：%s" % error, flush=True)
        print("=" * 58, flush=True)
        print(" 选技大乱斗 · 浮窗助手", flush=True)
        print(" %s 识别    %s 显示/隐藏    %s 退出" % (self.capture_key, self.toggle_key, self.quit_key), flush=True)
        requested = (self.args.capture_key, self.args.toggle_key, self.args.quit_key)
        actual = (self.capture_key, self.toggle_key, self.quit_key)
        if requested != actual:
            print(" （%s 被其他程序占用，已自动换键；可在 bat 里改回）" % ", ".join(requested), flush=True)
        print(" 浮窗常驻，可按住卡片任意位置拖动；%s 负责隐藏。" % self.toggle_key, flush=True)
        print(" 游戏建议使用「无边框窗口」模式；独占全屏无法显示浮窗。", flush=True)
        print("=" * 58, flush=True)
        self.start_server()
        if not self.args.no_ready:
            self.hud.show_ready(self.server_url)
        self.hud.root.after(50, self.poll)
        try:
            self.hud.root.mainloop()
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()

    # ------------------------------------------------------------------- loop
    def poll(self) -> None:
        for action, watcher in self.watchers.items():
            try:
                if watcher.pressed():
                    self.events.put(action)
            except Exception:
                pass
        try:
            while True:
                self.dispatch(self.events.get_nowait())
                if not self.running:
                    return
        except queue.Empty:
            pass
        if self.running:
            self.hud.root.after(50, self.poll)

    def dispatch(self, action: str) -> None:
        now = time.monotonic()
        cooldown = 2.5 if action == "capture" else 0.45
        if now - self._last_dispatch.get(action, 0.0) < cooldown:
            return
        self._last_dispatch[action] = now
        if action == "capture":
            self.capture_and_show()
        elif action == "toggle":
            self.hud.toggle(self.last_game_hwnd)
        elif action == "quit":
            self.quit()

    def capture_and_show(self) -> None:
        if self.busy:
            return
        self.busy = True
        started = time.perf_counter()
        try:
            hwnd = capture.find_game_window()
            if hwnd is None:
                foreground = capture.foreground_window()
                if capture.window_pid(foreground) == os.getpid():
                    # Focus is on our own HUD/console: no game to read.  Do not
                    # cover the previous result with an error card.
                    return
                hwnd = foreground
            self.last_game_hwnd = hwnd
            # hide the HUD so it cannot appear in the capture
            self.hud.hide()
            self.hud.root.update()
            time.sleep(0.20)
            shot = capture.capture(hwnd)
            if not self.args.no_save_capture:
                CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
                shot.image.save(CAPTURE_DIR / "last.png")
            print(
                "[capture] window=%r size=%dx%d method=%s %.2fs"
                % (shot.window_title, shot.image.width, shot.image.height, shot.method, shot.elapsed),
                flush=True,
            )
            self.hud.show(render_loading("正在识别英雄与流派…", self.toggle_key), hwnd)
            self.hud.root.update()

            self.recognizer.reload()
            self.advisor.reload()
            result = self.recognizer.analyze(shot.image)
            heroes = [h["name"] for h in result.get("heroes", []) if h.get("name")]
            enabled = [s["id"] for s in result["schools"]["enabled"]]
            banned = [s["id"] for s in result["schools"]["banned"]]
            warning = ""
            if len(heroes) < 3:
                warning = "有英雄未识别"
            if len(heroes) < 2 or not enabled:
                diag = result.get("diagnostics") or {}
                if not diag.get("panel_found", True):
                    message = "当前画面没有流派面板。"
                    hint = (
                        "没有找到右下角 13 流派面板和 5 个禁用红圈；如果画面只有 3 个英雄和 8 个底栏图标，"
                        "这一屏无法判断 8 启用 / 5 禁用。请等完整选人界面出现后再按 %s。" % self.capture_key
                    )
                elif len(heroes) < 2:
                    message = "英雄头像没有匹配。"
                    hint = (
                        "检测到流派面板，但只匹配到 %d/3 个英雄。自动识别目前只内置 3 个头像模板，"
                        "请到网页版手动选择并学习新英雄。" % len(heroes)
                    )
                else:
                    message = "没有识别到完整的英雄/流派信息。"
                    hint = "请确认画面停在开局选人界面，且 3 个英雄和右下角面板完整可见。"
                if not self.args.no_save_capture:
                    hint += "截图已保存到 data/captures/last.png。"
                self.hud.show(
                    render_error(message, hint, self.capture_key, self.toggle_key, self.quit_key),
                    hwnd,
                )
                return
            rec = self.advisor.recommend(heroes, enabled, banned)
            image = render_result(rec, shot, warning, self.capture_key, self.toggle_key, self.quit_key)
            self.hud.show(image, hwnd)
            top = (rec.get("recommendations") or [{}])[0]
            print(
                "[result] heroes=%s -> %s %.1f (%dms)"
                % (heroes, top.get("name", "?"), top.get("score", 0), int((time.perf_counter() - started) * 1000)),
                flush=True,
            )
        except Exception as exc:
            traceback.print_exc()
            try:
                self.hud.show(
                    render_error(
                        str(exc),
                        "游戏请使用无边框窗口模式；也可先用网页版上传截图。",
                        self.capture_key,
                        self.toggle_key,
                        self.quit_key,
                    ),
                    self.last_game_hwnd,
                )
            except Exception:
                pass
        finally:
            self.busy = False

    # ------------------------------------------------------------------ close
    def quit(self) -> None:
        self.running = False
        self.hotkeys.stop()
        if self.httpd is not None:
            try:
                self.httpd.shutdown()
            except Exception:
                pass
        self.shutdown()

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.hotkeys.stop()
        if self.httpd is not None:
            try:
                self.httpd.shutdown()
            except Exception:
                pass
        try:
            self.hud.close()
        except Exception:
            pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="选技大乱斗 · 浮窗助手")
    parser.add_argument("--capture-key", default="Alt+C", help="识别快捷键，默认 Alt+C")
    parser.add_argument("--toggle-key", default="Alt+X", help="显示/隐藏快捷键，默认 Alt+X")
    parser.add_argument("--quit-key", default="Ctrl+Alt+Q", help="退出快捷键，默认 Ctrl+Alt+Q")
    parser.add_argument("--port", type=int, default=8777, help="网页控制台端口，默认 8777")
    parser.add_argument("--alpha", type=float, default=0.97, help="浮窗不透明度")
    parser.add_argument("--hud-scale", type=float, default=0.0, help="浮窗缩放；0 表示按屏幕宽度自动")
    parser.add_argument("--no-server", action="store_true", help="不启动网页控制台")
    parser.add_argument("--no-ready", action="store_true", help="启动时不显示提示卡")
    parser.add_argument("--no-save-capture", action="store_true", help="不保存最近一次截图")
    args = parser.parse_args(argv)
    if not (0.5 <= args.alpha <= 1.0):
        print("--alpha 必须在 0.5~1.0 之间")
        return 2
    instance = acquire_single_instance()
    if instance is None:
        print("浮窗助手已经在运行了（或单实例锁不可用）。", flush=True)
        print("请使用屏幕上的浮窗，或先在旧控制台按 Ctrl+Alt+Q / 关闭控制台。", flush=True)
        return 0
    try:
        agent = Agent(args)
    except Exception as exc:
        print("浮窗启动失败：%s" % exc)
        traceback.print_exc()
        return 1
    agent.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
