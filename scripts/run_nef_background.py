"""Windowless Windows Task Scheduler entrypoint; never starts through Codex."""
import datetime
import os
from pathlib import Path
import sys
import traceback
import winreg


ROOT = Path(__file__).resolve().parents[1]


def main():
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    runtime = ROOT / ".runtime"
    runtime.mkdir(exist_ok=True)
    sys.stdout = (runtime / "nef-background.stdout.log").open(
        "a", encoding="utf-8", buffering=1
    )
    sys.stderr = (runtime / "nef-background.stderr.log").open(
        "a", encoding="utf-8", buffering=1
    )
    print(f"\nNEF background start {datetime.datetime.now().isoformat()} PID={os.getpid()}")
    # The scheduler may have an older environment than the user's saved setting.
    # Read only this application's existing key, never write or log its value.
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as environment:
            key, _ = winreg.QueryValueEx(environment, "NEF_COMPOSER_API_KEY")
            if isinstance(key, str) and key:
                os.environ["NEF_COMPOSER_API_KEY"] = key
    except FileNotFoundError:
        pass
    (runtime / "nef.pid").write_text(str(os.getpid()) + "\n", encoding="ascii")
    from start import main as start_nef

    start_nef()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
