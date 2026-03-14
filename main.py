import threading
import subprocess
import socket
import time
from webpage import *
from ad_slides import ThelabApp

def check_internet(timeout=3):
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        return True
    except:
        return False


def ask_for_wifi():
    """
    Open Linux WiFi GUI or TUI.
    """
    # 1) Try the graphical editor
    try:
        subprocess.Popen(["nm-connection-editor"])
        return
    except:
        pass

    # 2) Fallback → nmtui in terminal
    try:
        subprocess.Popen(["x-terminal-emulator", "-e", "nmtui"])
    except:
        print("⚠️ Could not open WiFi settings. Install NetworkManager tools.")


def run_flask():
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":

    # --------------------------------------
    # Wait for internet
    # --------------------------------------
    while not check_internet():
        print("❌ No internet detected")
        print("📡 Opening WiFi setup...")
        ask_for_wifi()
        print("⏳ Waiting for internet...")
        time.sleep(5)  # wait a bit before checking again

    print("✅ Internet OK")

    # --------------------------------------
    # Run Flask in background
    # --------------------------------------
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("🚀 Flask server started")

    # --------------------------------------
    # Start pygame App
    # --------------------------------------
    app = ThelabApp()
    app.run()
