# ← Console client: basic text chat over WebSocket
import asyncio
import websockets

async def receive_messages(websocket):
    while True:
        try:
            message = await websocket.recv()
            print(f"\nFriend: {message}")

        except:
            print("\nDisconnected from server")
            break

async def send_messages(websocket):
    while True:
        message = await asyncio.to_thread(input, "You: ")

        if message.strip() != "":
            await websocket.send(message)

async def chat():

    uri = "wss://wan-data-t.onrender.com/ws"

    async with websockets.connect(uri) as websocket:

        receive_task = asyncio.create_task(
            receive_messages(websocket)
        )

        send_task = asyncio.create_task(
            send_messages(websocket)
        )

        await asyncio.gather(receive_task, send_task)

asyncio.run(chat())