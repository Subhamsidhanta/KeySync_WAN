# ← Console client: basic text chat over WebSocket
import asyncio
import logging
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

# =========================
# LOGGING  (FIX #2)
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

URI = "wss://wan-data-t.onrender.com/ws"
MAX_RECONNECT_DELAY = 60   # FIX #1 — cap for exponential backoff


async def receive_messages(websocket):
    while True:
        try:
            message = await websocket.recv()
            print(f"\nFriend: {message}")

        # FIX #2 — specific exceptions instead of bare except
        except ConnectionClosed as e:
            log.warning("Disconnected from server: %s", e)
            break
        except WebSocketException as e:
            log.error("WebSocket error: %s", e, exc_info=True)
            break
        except OSError as e:
            log.error("Network error: %s", e, exc_info=True)
            break


async def send_messages(websocket):
    while True:
        try:
            message = await asyncio.to_thread(input, "You: ")
            if message.strip():
                await websocket.send(message)

        # FIX #2 — specific exceptions
        except ConnectionClosed as e:
            log.warning("Connection closed while sending: %s", e)
            break
        except WebSocketException as e:
            log.error("WebSocket error while sending: %s", e, exc_info=True)
            break
        except OSError as e:
            log.error("Network error while sending: %s", e, exc_info=True)
            break
        except EOFError:
            break  # stdin closed (e.g. piped input finished)


async def chat():
    """
    FIX #1 — Automatic reconnection with exponential back-off.
    Starts at 2 s, doubles on each failure, caps at MAX_RECONNECT_DELAY.
    """
    delay = 2  # initial reconnect delay in seconds

    while True:
        try:
            log.info("Connecting to %s ...", URI)
            async with websockets.connect(URI, open_timeout=15) as websocket:
                log.info("Connected ✓")
                delay = 2  # reset backoff on successful connection

                receive_task = asyncio.create_task(receive_messages(websocket))
                send_task    = asyncio.create_task(send_messages(websocket))

                done, pending = await asyncio.wait(
                    [receive_task, send_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                # Cancel the surviving task on disconnect
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

        # FIX #1 + FIX #2 — specific exceptions with logging
        except ConnectionClosed as e:
            log.warning("Disconnected: %s", e)
        except WebSocketException as e:
            log.error("WebSocket error: %s", e, exc_info=True)
        except OSError as e:
            log.error("Network error: %s", e, exc_info=True)
        except asyncio.CancelledError:
            log.info("Cancelled, shutting down.")
            break

        log.info("Reconnecting in %ds... (exponential backoff)", delay)
        await asyncio.sleep(delay)
        delay = min(delay * 2, MAX_RECONNECT_DELAY)  # FIX #1 — exponential backoff


asyncio.run(chat())