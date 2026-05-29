# ← Debug tool: local keyboard listener only
from pynput import keyboard

typed_keys = ""

def on_press(key):
    global typed_keys

    try:
        typed_keys += key.char
    except AttributeError:
        typed_keys += f"[{key}]"

    print("Saved:", typed_keys)

    # Stop on ESC
    if key == keyboard.Key.esc:
        return False

with keyboard.Listener(on_press=on_press) as listener:
    listener.join()


