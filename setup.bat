@echo off
title TeamTalk AI Bot - Setup
color 0A
echo.
echo  ==============================================
echo     TeamTalk 5 AI Bot - Auto Setup
echo  ==============================================
echo.
echo [1/5] Checking Python...
python --version >/dev/null 2>&1
if %%errorlevel%% neq 0 (
    echo Python NOT installed!
    echo Install from: https://www.python.org/downloads/
    start https://www.python.org/downloads/
    pause
    exit /b
)
python --version
echo Python OK!
echo.
echo [2/5] Upgrading pip...
python -m pip install --upgrade pip --quiet 2>/dev/null
echo.
echo [3/5] Installing packages...
python -m pip install teamtalk.py --quiet 2>/dev/null
python -m pip install requests --quiet 2>/dev/null
echo Packages installed!
echo.
echo [4/5] Checking TeamTalk SDK...
python -c "import teamtalk" 2>/dev/null
if %%errorlevel%% neq 0 (echo SDK will auto-download on first run)
echo.
echo [5/5] Config check...
if not exist config.json (
    python -c "import json;d={};d[chr(115)+chr(101)+chr(114)+chr(118)+chr(101)+chr(114)]={chr(104)+chr(111)+chr(115)+chr(116):chr(108)+chr(111)+chr(99)+chr(97)+chr(108)+chr(104)+chr(111)+chr(115)+chr(116)};json.dump(d,open(chr(99)+chr(111)+chr(110)+chr(102)+chr(105)+chr(103)+chr(46)+chr(106)+chr(115)+chr(111)+chr(110),chr(119)),indent=2)"
    echo config.json created!
) else (echo config.json exists)
echo.
echo ==============================================
echo   Setup Complete!
echo ==============================================
echo.
echo   1. Edit config.json with your API key
echo   2. Edit config.json with server info
echo   3. Double-click run.bat to start!
echo.
echo   Free API keys:
echo     OpenRouter: https://openrouter.ai/keys
echo     Groq:       https://console.groq.com/keys
echo     Gemini:     https://aistudio.google.com/apikey
echo ==============================================
pause