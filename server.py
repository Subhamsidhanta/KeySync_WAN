# ← FastAPI WebSocket relay server
from fastapi import FastAPI, WebSocket
import uvicorn

app = FastAPI()

clients = []

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):

    await websocket.accept()
    clients.append(websocket)

    print("Client connected")

    try:
        while True:

            data = await websocket.receive_text()

            print("Received:", data)

            for client in clients:
                await client.send_text(data)

    except Exception as e:
        print("Error:", e)

    finally:
        clients.remove(websocket)
        print("Client disconnected")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)