@echo off
title Crypto News Bot
echo =========================================
echo    Crypto News Bot - Starting...
echo =========================================
echo.

cd /d "%~dp0"

:: Use the full Python path
set PYTHON_PATH=C:\Users\damdam\AppData\Local\Programs\Python\Python312\python.exe

:: Install dependencies if needed
"%PYTHON_PATH%" -m pip install -r requirements.txt --quiet

:: Run the bot
"%PYTHON_PATH%" crypto_news_bot.py

pause
