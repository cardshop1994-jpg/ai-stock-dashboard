@echo off
chcp 65001 >nul
title AI関連株 監視ダッシュボード
REM Python のパスが違う場合はここを調整してください。
"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%~dp0site_server.py"
pause
