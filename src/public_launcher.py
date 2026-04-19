import os
import signal
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.ngrok_utils import NgrokManager


def main():
    root_dir = Path(__file__).resolve().parent.parent
    os.chdir(root_dir)
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
    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(" RAE ENTERPRISE PUBLIC LAUNCHER")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Public URL: {url}")
    print("Open this URL on your Android phone (any network).")
    print()
    cmd = [
        "streamlit",
        "run",
        "src/dashboard.py",
        "--server.address",
        "0.0.0.0",
        "--server.port",
        "8501",
    ]
    proc = subprocess.Popen(cmd)

    def handle_sigint(signum, frame):
        try:
            manager.stop_tunnel()
        finally:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    try:
        proc.wait()
    finally:
        manager.stop_tunnel()


if __name__ == "__main__":
    main()

