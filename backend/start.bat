@echo off
cd /d "%~dp0"
call "%~dp0venv\Scripts\activate.bat"
"%~dp0venv\Scripts\python.exe" run_server.py
