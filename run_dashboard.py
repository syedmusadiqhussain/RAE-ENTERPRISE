import os
import socket
import subprocess
import time
import sys


def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def main():
    addr = os.getenv("STREAMLIT_SERVER_ADDRESS", "localhost")
    port = os.getenv("STREAMLIT_SERVER_PORT", "8501")
    dashboard_cmd = [
        "streamlit",
        "run",
        "src/dashboard.py",
        "--server.address",
        addr,
        "--server.port",
        port,
    ]
    print(f"Dashboard URL: http://localhost:{port}")
    dashboard = subprocess.Popen(dashboard_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        while True:
            line = dashboard.stdout.readline()
            if not line:
                break
            sys.stdout.write(line.decode(errors="ignore"))
    except KeyboardInterrupt:
        dashboard.terminate()


if __name__ == "__main__":
    main()
