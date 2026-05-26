"""
run_server.py
-------------
Starts uvicorn programmatically so no shell glob-expansion or line-continuation
issues can corrupt the arguments.

Run directly:  python run_server.py
Or via bat:    start.bat
"""

import os
import sys
import subprocess

# Always run from the directory this file lives in
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Use the same Python / uvicorn that's running this script
uvicorn_exe = os.path.join(os.path.dirname(sys.executable), "uvicorn.exe")
if not os.path.exists(uvicorn_exe):
    uvicorn_exe = os.path.join(os.path.dirname(sys.executable), "uvicorn")
if not os.path.exists(uvicorn_exe):
    uvicorn_exe = "uvicorn"  # fall back to PATH

args = [
    uvicorn_exe,
    "app:app",
    "--host", "0.0.0.0",
    "--port", "8000",
    "--reload",
    "--reload-dir", ".",
]

print(f"Starting uvicorn from: {os.getcwd()}")
print(f"Command: {' '.join(args)}")

subprocess.run(args)
