from fastapi import FastAPI, WebSocket
import uvicorn
import os

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

                # Don't send back to sender
                if client != websocket:
                    await client.send_text(data)

    except Exception as e:
        print("Error:", e)

    finally:

        clients.remove(websocket)
        print("Client disconnected")

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 8000))

    uvicorn.run(app, host="0.0.0.0", port=port)
