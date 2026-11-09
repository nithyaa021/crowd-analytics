@echo off
REM Starts the Crowd Density and Bottleneck Analytics dashboard on Windows.
REM Why a .bat file: the heavy lifting (model loading, video loop) must start with the correct
REM virtual environment, and double-clicking one file is the easiest thing to do before a demo.

REM Work from the folder this file lives in, whatever the shortcut's "start in" happens to be.
cd /d "%~dp0"

REM Fail loudly if the environment is missing, instead of a confusing "uvicorn not found".
if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found.
    echo Create it with:  py -3.12 -m venv .venv
    echo Then install:    .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

REM The model and OpenCV must run inside .venv, so activate it first.
call ".venv\Scripts\activate.bat"

REM Open the browser a moment later, so the page loads once the server is listening.
REM "start" returns immediately, which is why it does not block uvicorn below.
start "" cmd /c "timeout /t 4 >nul & start "" http://127.0.0.1:8000"

REM Start the server. --host 127.0.0.1 keeps it local: this is a demo, not a public service.
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

REM If uvicorn exits (Ctrl+C), keep the window open so the error can be read.
pause
