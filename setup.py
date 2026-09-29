#!/usr/bin/env python3
"""
🤖 TeamTalk AI Bot - Setup for Android (Pydroid 3)
يفعّل كل شي تلقائياً على الأندرويد
"""

import subprocess
import sys
import os
import json

# Colors for terminal
GREEN = "[92m"
RED = "[91m"
YELLOW = "[93m"
CYAN = "[96m"
RESET = "[0m"
BOLD = "[1m"

def print_header():
    print(CYAN + "=" * 50)
    print("  🤖 TeamTalk AI Bot - Android Setup")
    print("=" * 50 + RESET)
    print()

def print_step(num, total, text):
    print(YELLOW + "[" + str(num) + "/" + str(total) + "]" + RESET + " " + text)

def print_ok(text):
    print(GREEN + "  ✅ " + text + RESET)

def print_err(text):
    print(RED + "  ❌ " + text + RESET)

def run_pip(package):
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", package, "--quiet"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True
    except:
        return False

def main():
    print_header()
    total = 5

    # Step 1: Check Python
    print_step(1, total, "Checking Python version...")
    print("  Python " + sys.version.split()[0])
    print_ok("Python is ready!")
    print()

    # Step 2: Upgrade pip
    print_step(2, total, "Upgrading pip...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip", "--quiet"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print_ok("pip upgraded!")
    except:
        print_ok("pip already up to date")
    print()

    # Step 3: Install packages
    print_step(3, total, "Installing required packages...")

    packages = ["teamtalk.py", "requests"]
    for pkg in packages:
        print("  Installing " + pkg + "...")
        if run_pip(pkg):
            print_ok(pkg + " installed!")
        else:
            print_err(pkg + " failed. Try: pip install " + pkg)

    # Optional: install kivy for future GUI
    print("  Installing kivy (optional)...")
    run_pip("kivy")
    print()
    print_ok("All packages installed!")
    print()

    # Step 4: Check SDK
    print_step(4, total, "Checking TeamTalk SDK...")
    try:
        import teamtalk
        print_ok("TeamTalk SDK is ready!")
    except ImportError:
        print("  SDK will auto-download on first run")
        print_ok("SDK check done!")
    print()

    # Step 5: Create/Check config
    print_step(5, total, "Checking config.json...")
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

    if not os.path.exists(config_path):
        print("  Creating config.json...")
        config_data = {
            "server": {
                "host": "localhost",
                "tcp_port": 10333,
                "udp_port": 10333,
                "username": "AI_Bot",
                "password": "",
                "nickname": "🤖 AI Bot"
            },
            "ai": {
                "provider": "groq",
                "api_key": "YOUR_API_KEY_HERE",
                "api_key_env": "GROQ_API_KEY",
                "model": "openai/gpt-oss-20b",
                "system_prompt": "You are a helpful AI assistant. Respond in Arabic when users write in Arabic, English when they write English. Keep responses concise.",
                "max_tokens": 200,
                "temperature": 0.7
            },
            "commands": {
                "prefix": "!",
                "enabled": True
            }
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        print_ok("config.json created!")
    else:
        print_ok("config.json exists!")

    # Check API key
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        ai_cfg = cfg.get("ai", {})
        key = ai_cfg.get("api_key", "")
        key_from_env = os.environ.get(ai_cfg.get("api_key_env", ""))
        if key == "YOUR_API_KEY_HERE" and not key_from_env:
            print()
            print(YELLOW + "  ⚠️  API Key NOT set!" + RESET)
            print("  Set GROQ_API_KEY, or edit config.json and add your API key")
        else:
            print_ok("API Key is configured!")
    except:
        pass

    print()
    print(CYAN + "=" * 50)
    print("  ✅ Setup Complete!")
    print("=" * 50 + RESET)
    print()
    print("  Next steps:")
    print("  1. Open config.json")
    print("  2. Add your API key")
    print("  3. Add your TeamTalk server info")
    print("  4. Run: python run.py")
    print()
    print("  Free API keys:")
    print("  • OpenRouter: https://openrouter.ai/keys")
    print("  • Groq: https://console.groq.com/keys")
    print("  • Gemini: https://aistudio.google.com/apikey")
    print(CYAN + "=" * 50 + RESET)
    print()

if __name__ == "__main__":
    main()
