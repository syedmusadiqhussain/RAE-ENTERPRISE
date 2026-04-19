import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def ensure_package(module_name, install_name=None):
    try:
        __import__(module_name)
        return True
    except ImportError:
        name = install_name or module_name
        print(f"Installing missing dependency: {name}...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        print(result.stdout)
        try:
            __import__(module_name)
            return True
        except ImportError:
            print(f"Failed to import {module_name} after installation.")
            return False


def kill_port_8501_windows():
    if os.name != "nt":
        return
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for line in result.stdout.splitlines():
            if ":8501" in line and "LISTENING" in line:
                parts = line.split()
                if parts:
                    pid = parts[-1]
                    try:
                        subprocess.run(
                            ["taskkill", "/PID", pid, "/F"],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                        )
                    except Exception:
                        pass
    except Exception:
        pass


def main():
    root = Path(__file__).resolve().parent
    os.chdir(root)
    ok = True
    ok = ok and ensure_package("pyngrok")
    ok = ok and ensure_package("streamlit")
    ok = ok and ensure_package("dotenv", "python-dotenv")
    if not ok:
        print("Dependency installation failed. Exiting.")
        sys.exit(1)
    from dotenv import load_dotenv
    from src.ngrok_utils import NgrokManager
    load_dotenv()
    token = os.getenv("NGROK_AUTH_TOKEN", "")
    if not token:
        print("NGROK_AUTH_TOKEN is not set in .env. Please add it and rerun.")
        sys.exit(1)
    print("Checking port 8501...")
    kill_port_8501_windows()
    print("Starting backend engine (main.py)...")
    main_proc = subprocess.Popen([sys.executable, "main.py"])
    print("Starting dashboard (run_dashboard.py)...")
    dash_proc = subprocess.Popen([sys.executable, "run_dashboard.py"])
    print("Waiting for dashboard to initialize...")
    time.sleep(8)
    print("Starting secure ngrok tunnel on port 8501...")
    manager = NgrokManager(token)
    url = manager.start_tunnel(port=8501)
    if not url:
        print("Failed to start ngrok tunnel.")
        main_proc.terminate()
        dash_proc.terminate()
        sys.exit(1)
    print()
    print("════════════════════════════════════════")
    print(" RAE ENTERPRISE LIVE DELIVERY READY")
    print("════════════════════════════════════════")
    print(f" Public URL: {url}")
    print()
    print("Share this URL with your client. They can open it on any device.")
    print("Press Ctrl+C to stop services and close the tunnel.")

    def handle_sigint(signum, frame):
        try:
            manager.stop_tunnel()
        except Exception:
            pass
        for proc in (dash_proc, main_proc):
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
        dash_proc.wait()
    finally:
        try:
            manager.stop_tunnel()
        except Exception:
            pass
        try:
            main_proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    main()

