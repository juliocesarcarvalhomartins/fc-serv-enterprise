from __future__ import annotations

import os
import socket
import threading
import webbrowser

import uvicorn


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 80))
            return str(sock.getsockname()[0])
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


def main() -> None:
    host = os.getenv("FATURA_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("FATURA_SERVER_PORT", "8080"))
    address = local_ip()
    print("=" * 62)
    print("FC SERV - SERVIDOR CENTRAL")
    print("=" * 62)
    print(f"Neste computador: http://127.0.0.1:{port}")
    print(f"Nas outras máquinas da rede: http://{address}:{port}")
    print("Mantenha esta janela aberta enquanto o sistema estiver em uso.")
    print("Não exponha esta porta diretamente na internet sem HTTPS.")
    print("=" * 62)
    threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    uvicorn.run("app.main:app", host=host, port=port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
