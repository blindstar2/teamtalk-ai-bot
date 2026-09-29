#!/usr/bin/env python3
"""
🤖 TeamTalk AI Bot - Run (Android/Pydroid 3)
"""

import subprocess
import sys
import os

# Get the directory of this script
DIR = os.path.dirname(os.path.abspath(__file__))
BOT_FILE = os.path.join(DIR, "bot.py")

GREEN = "[92m"
CYAN = "[96m"
RESET = "[0m"

def main():
    print(CYAN + "=" * 50)
    print("  🤖 TeamTalk AI Bot")
    print("=" * 50 + RESET)
    print()

    # Check if bot.py exists
    if not os.path.exists(BOT_FILE):
        print("  ❌ bot.py not found!")
        print("  Make sure all files are in the same folder.")
        return

    # Check config
    config_file = os.path.join(DIR, "config.json")
    if os.path.exists(config_file):
        import json
        with open(config_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        key = cfg.get("ai", {}).get("api_key", "")
        if key == "YOUR_API_KEY_HERE":
            print("  ⚠️  API Key not set!")
            print("  Edit config.json first!")
            print()
            return
        print("  Server: " + cfg["server"]["host"])
        print("  AI: " + cfg["ai"]["provider"].title())
        print("  Model: " + cfg["ai"]["model"])
        print()

    print("  Starting bot... (Press Ctrl+C to stop)")
    print(GREEN + "=" * 50 + RESET)
    print()

    # Run bot.py
    try:
        subprocess.run([sys.executable, BOT_FILE])
    except KeyboardInterrupt:
        print()
        print("  Bot stopped. 👋")

if __name__ == "__main__":
    main()
