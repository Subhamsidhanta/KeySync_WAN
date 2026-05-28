import asyncio
import websockets

async def receive_messages(websocket):
    while True:
        try:
            message = await websocket.recv()
            print(f"\nReceived: {message}")
        except:
            print("Disconnected from server")
            break

async def send_messages(websocket):
    while True:
        message = await asyncio.to_thread(input, "Enter message to send: ")
        await websocket.send(message)

async def chat():
    uri = "ws://10.227.197.153:8000/ws"

    async with websockets.connect(uri) as websocket:

        receive_task = asyncio.create_task(
            receive_messages(websocket)
        )

        send_task = asyncio.create_task(
            send_messages(websocket)
        )

        await asyncio.gather(receive_task, send_task)

asyncio.run(chat())