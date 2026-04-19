import os
import signal
import subprocess
import sys

import pyperclip
import pyqrcode
from dotenv import load_dotenv

from src.ngrok_utils import NgrokManager


def main():
    load_dotenv()
    token = os.getenv("NGROK_AUTH_TOKEN", "")
    if not token:
        print("NGROK_AUTH_TOKEN is not set in .env")
        sys.exit(1)
    manager = NgrokManager(token)
    url = manager.start_tunnel(port=8501)
    if not url:
        print("Failed to start ngrok tunnel.")
        sys.exit(1)
    print(f"📱 Mobile URL: `{url}`")
    qr = pyqrcode.create(url)
    qr.png("ngrok_qr.png", scale=6)
    try:
        pyperclip.copy(url)
        print("✅ URL copied to clipboard")
    except Exception:
        print("Clipboard copy not available on this system.")
    print("QR Code saved: ngrok_qr.png")
    print("Scan QR code or copy URL to phone")
    addr = os.getenv("STREAMLIT_SERVER_ADDRESS", "0.0.0.0")
    port = os.getenv("STREAMLIT_SERVER_PORT", "8501")
    cmd = [
        "streamlit",
        "run",
        "src/dashboard.py",
        "--server.address",
        addr,
        "--server.port",
        port,
    ]
    proc = subprocess.Popen(cmd)

    def handle_sigint(signum, frame):
        manager.stop_tunnel()
        proc.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    proc.wait()


if __name__ == "__main__":
    main()

