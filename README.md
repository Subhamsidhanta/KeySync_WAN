<div align="center">

# 🔑 KeySync

### Real-Time Keystroke Synchronization Over WAN

**Capture. Buffer. Sync. Broadcast.**

[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Server-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![WebSockets](https://img.shields.io/badge/WebSockets-Full--Duplex-4A90D9?style=for-the-badge&logo=socket.io&logoColor=white)](https://websockets.readthedocs.io/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![Deployed On](https://img.shields.io/badge/Hosted%20on-Render-46E3B7?style=for-the-badge&logo=render&logoColor=white)](https://render.com/)

APP- https://drive.google.com/drive/folders/1mr1E-9Mutk2LBlXOSMebroh3-CDnQXQx?usp=sharing
---

*A lightweight Python tool that captures global keystrokes on Windows, intelligently buffers typed words, and broadcasts them in real-time to all connected clients over the internet via WebSockets.*

</div>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Architecture](#-architecture)
- [Project Structure](#-project-structure)
- [How It Works](#-how-it-works)
- [Tech Stack](#-tech-stack)
- [Getting Started](#-getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
- [Usage](#-usage)
  - [Run the Server](#1-run-the-relay-server)
  - [Run the Tray Client](#2-run-the-system-tray-client)
  - [Other Clients](#3-other-client-modes)
- [Build Executable](#-build-standalone-executable)
- [Configuration](#-configuration)
- [Known Issues](#-known-issues)

---

## 🌐 Overview

**KeySync** is a real-time WAN keystroke synchronization system. It runs a global keyboard hook in the background, groups individual keystrokes into buffered words, and sends them through a central WebSocket relay server to all connected sessions — live.

The primary client (`tray.py`) operates entirely in the **Windows System Tray** — no window, no console, just a small icon. It uses **three threads** working in unison: one for the system tray UI, one for the keyboard listener, and one for the async WebSocket connection.

---

## ✨ Features

| Feature | Description |
|---|---|
| ⚡ **Smart Word Buffering** | Characters are grouped locally and flushed as complete words on `Space` — reducing unnecessary network calls |
| 🌐 **WAN Broadcasting** | All connected clients receive keystrokes in real-time over the internet |
| 🎹 **Action Key Mapping** | Special keys like `Backspace`, `Enter`, `Tab`, `Delete`, and arrow keys are formatted as readable tags (e.g., `[Backspace]`, `[↑]`) |
| 🕹️ **Modifier Key Combos** | Detects and formats Ctrl/Alt combinations like `[Ctrl+C]`, `[Ctrl+Alt+A]` |
| 👻 **Silent Tray Mode** | Runs invisibly in the Windows System Tray with a right-click Exit option |
| 📦 **Standalone .exe Build** | PyInstaller spec included to compile to a windowless, portable executable |
| ☁️ **Cloud Deployed** | Server is hosted on [Render](https://render.com) and ready to use at `wss://wan-data-t.onrender.com/ws` |

---

## 🏗️ Architecture

KeySync uses a **Hub-and-Spoke** relay model. All clients connect to a central server that simply receives and re-broadcasts every message to every connected socket.

```
┌─────────────────────────────────────────────────────┐
│                RELAY SERVER (server.py)              │
│             wss://wan-data-t.onrender.com/ws         │
│                                                      │
│   clients = [ws1, ws2, ws3, ...]                     │
│   on_message → broadcast to ALL clients              │
└───────────────────────┬─────────────────────────────┘
                        │  WebSocket (Full-Duplex)
          ┌─────────────┼──────────────┐
          │             │              │
          ▼             ▼              ▼
   ┌─────────────┐  ┌──────────┐  ┌──────────┐
   │  tray.py    │  │  a.py    │  │ client.py│
   │ (Tray App)  │  │ (CLI Key │  │ (CLI Chat│
   │             │  │  Sender) │  │  Client) │
   │ ┌─────────┐ │  └──────────┘  └──────────┘
   │ │ KB Hook │ │
   │ └────┬────┘ │
   │      ▼      │
   │ ┌─────────┐ │
   │ │  Queue  │ │  ← Thread-safe buffer
   │ └────┬────┘ │
   │      ▼      │
   │ ┌─────────┐ │
   │ │  WS Loop│ │  ← Async WebSocket client
   │ └─────────┘ │
   │ ┌─────────┐ │
   │ │  pystray│ │  ← System Tray UI (Main Thread)
   │ └─────────┘ │
   └─────────────┘
```

---

## 📁 Project Structure

```
WAN_DATA transfer/
│
├── server.py          # ← FastAPI WebSocket relay server
├── tray.py            # ← Primary client: System Tray + KB Hook + WS
├── a.py (keys_per_char.py)               # ← Console client: sends raw keys per-character
├── client.py          # ← Console client: basic text chat over WebSocket
├── key_listen.py               # ← Debug tool: local keyboard listener only
│
├── tray.spec          # ← PyInstaller build config for tray.py → tray.exe
├── procfile           # ← Render/Heroku startup command
├── requirments.txt    # ← Server-side pip dependencies
│
├── build/             # ← PyInstaller build artifacts (auto-generated)
└── dist/              # ← Compiled tray.exe lives here after build
```

---

## 🧠 How It Works

### The Smart Buffer (`tray.py`)

Rather than blasting the network with every single keystroke, `tray.py` uses a local character buffer and only transmits complete words or actions:

```
Key Pressed
     │
     ▼
Is it a Modifier? (Ctrl / Alt / Shift)
     │ Yes → Update modifier flag, return silently
     │ No  ↓
     ▼
Is it a printable character?
     │ Yes → Append to typed_buffer
     │ No  ↓
     ▼
Is it Space?
     │ Yes → Flush typed_buffer as a word to Queue → send
     │ No  ↓
     ▼
Is it a Special Key? (Enter, Backspace, Arrow...)
     │ Yes → Flush typed_buffer (if any) → send "[Key]" tag to Queue
     │
     ▼
WebSocket loop dequeues and sends to relay server
```

### Special Key Labels

| Keystroke | Sent as |
|---|---|
| `Enter` | `[Enter]` |
| `Backspace` | `[Backspace]` |
| `Delete` | `[Delete]` |
| `Tab` | `[Tab]` |
| `Escape` | `[Esc]` |
| `↑ ↓ ← →` | `[↑]` `[↓]` `[←]` `[→]` |
| `Ctrl + C` | `[Ctrl+C]` |
| `Ctrl + Alt + A` | `[Ctrl+Alt+A]` |
| `F1` – `F12` | `[F1]` – `[F12]` |

### Threading Model (`tray.py`)

```
Main Thread         →  pystray.Icon event loop (Tray UI + Exit menu)
Background Thread 1 →  pynput keyboard.Listener (global KB hook)
Background Thread 2 →  asyncio event loop (WebSocket send + receive)
```

The background threads are `daemon=True`, so they exit automatically when the main tray thread is killed.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Server Framework** | [FastAPI](https://fastapi.tiangolo.com/) |
| **ASGI Server** | [Uvicorn](https://www.uvicorn.org/) |
| **WebSockets (Client)** | [websockets](https://websockets.readthedocs.io/) |
| **Keyboard Hook** | [pynput](https://pynput.readthedocs.io/) |
| **System Tray UI** | [pystray](https://pystray.readthedocs.io/) |
| **Image Drawing** | [Pillow (PIL)](https://pillow.readthedocs.io/) |
| **Executable Builder** | [PyInstaller](https://pyinstaller.org/) |
| **Cloud Hosting** | [Render](https://render.com/) |

---

## 🚀 Getting Started

### Prerequisites

- Python **3.8 or higher**
- Windows OS *(required for `pynput` global hooks and `pystray` tray integration)*
- pip

---

### Installation

**1. Clone the repository**

```bash
git clone https://github.com/Subhamsidhanta/WAN-DATA-T.git
cd "WAN-DATA-T"
```

**2. Install server dependencies**

```bash
pip install -r requirments.txt
```

**3. Install client-side dependencies**

```bash
pip install pynput pystray pillow
```

> ℹ️ The `requirments.txt` only covers the server. Client-specific packages (`pynput`, `pystray`, `pillow`) must be installed separately.

---

## 🖥️ Usage

### 1. Run the Relay Server

> Skip this if you want to use the already-hosted cloud server at `wss://wan-data-t.onrender.com/ws`

```bash
python server.py
```

The server starts at `http://0.0.0.0:8000`. Clients connect via `ws://localhost:8000/ws`.

---

### 2. Run the System Tray Client

```bash
python tray.py
```

- A small **green square icon** appears in your Windows System Tray.
- Your keystrokes are silently captured, buffered, and broadcast to all connected sessions.
- **Right-click the tray icon** → click **Exit** to stop the application.

---

### 3. Other Client Modes

**Basic Chat Client** (manual text input):
```bash
python client.py
```

**Raw Key Sender** (sends each key immediately, no buffering):
```bash
python a.py
```
Press `Esc` to disconnect.

**Local Keyboard Debug Tool** (no network, local only):
```bash
python key_listen.py
```
Press `Esc` to stop listening.

---

## 📦 Build Standalone Executable

Compile `tray.py` into a single `.exe` with no console window using the included PyInstaller spec:

**1. Install PyInstaller**
```bash
pip install pyinstaller
```

**2. Build**
```bash
pyinstaller tray.spec
```

**3. Output**

The executable is generated at:
```
dist/tray.exe
```

It runs completely silently in the background — no terminal, no pop-up. Only the System Tray icon is visible.

---

## ⚙️ Configuration

### Switching Between Local and Cloud Server

All client files (`tray.py`, `a.py`, `client.py`) contain a hardcoded URI at the top:

```python
# Current (Cloud / Production)
URI = "wss://wan-data-t.onrender.com/ws"

# For local development
URI = "ws://localhost:8000/ws"
```

Change this variable to point to your local server when developing.

---

## ⚠️ Known Issues

| Issue | Detail |
|---|---|
| **Typo in dependency file** | The file is named `requirments.txt` instead of `requirements.txt`. This is harmless but non-standard. |
| **Missing client deps in requirements** | `pynput`, `pystray`, and `pillow` are not in `requirments.txt`. They must be installed manually. |
| **Broadcast loopback** | The server broadcasts to **all** connected clients including the sender. The sender will see their own keystrokes echoed back as `Friend: <message>`. |
| **Windows-only client** | `pynput` global hooks and `pystray` tray integration are designed for Windows. The server (`server.py`) is cross-platform. |

---

<div align="center">

Made with ❤️ by [Subham Sidhanta](https://github.com/Subhamsidhanta)

</div>
