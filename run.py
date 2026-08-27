from __future__ import annotations

import socket
import threading
import webbrowser

import uvicorn


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> None:
    port = available_port()
    url = f"http://127.0.0.1:{port}"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()

