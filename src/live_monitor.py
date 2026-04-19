import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError


def is_windows():
    return os.name == "nt"


def check_processes():
    running_main = False
    running_dashboard = False
    try:
        if is_windows():
            result = subprocess.run(
                ["wmic", "process", "get", "CommandLine"],
                capture_output=True,
                text=True,
            )
            output = result.stdout.lower()
        else:
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True,
            )
            output = result.stdout.lower()
        if "main.py" in output:
            running_main = True
        if "run_dashboard.py" in output:
            running_dashboard = True
    except Exception:
        pass
    return running_main, running_dashboard


def tail_log(path, lines=20):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.readlines()
        return content[-lines:]
    except Exception:
        return []


def check_dashboard(url="http://localhost:8501"):
    try:
        with urlopen(url, timeout=2) as resp:
            return resp.status == 200
    except URLError:
        return False
    except Exception:
        return False


def clear_screen():
    if is_windows():
        os.system("cls")
    else:
        os.system("clear")


def main():
    root_dir = Path(__file__).resolve().parent.parent
    log_path = str(root_dir / "logs" / "app.log")
    while True:
        clear_screen()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print("=" * 80)
        print(f"RAE LIVE MONITOR {now}")
        print("=" * 80)
        running_main, running_dashboard = check_processes()
        print("Process Status")
        print("-" * 80)
        print(f"main.py         : {'RUNNING' if running_main else 'STOPPED'}")
        print(f"run_dashboard.py: {'RUNNING' if running_dashboard else 'STOPPED'}")
        print()
        print("Dashboard Connectivity")
        print("-" * 80)
        ok = check_dashboard()
        print(f"http://localhost:8501: {'OK' if ok else 'UNREACHABLE'}")
        print()
        print(f"Tail logs/app.log (last 20 lines)")
        print("-" * 80)
        lines = tail_log(log_path, 20)
        if not lines:
            print("No log data available.")
        else:
            for line in lines:
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"[{ts}] {line.rstrip()}")
        print()
        print("Refreshing in 5 seconds... (Ctrl+C to stop)")
        time.sleep(5)


if __name__ == "__main__":
    main()
