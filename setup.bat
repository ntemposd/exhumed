@echo off
REM EXHUMED - Setup Script (Windows)
setlocal enabledelayedexpansion

echo ==================================================
echo  EXHUMED - Setup (Windows)
echo ==================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python 3.9+ is required and was not found in PATH.
    exit /b 1
)

npm --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: npm is required for the Next.js frontend and was not found in PATH.
    exit /b 1
)

if not exist ".venv" (
    echo Creating virtual environment in .venv ...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create virtual environment.
        exit /b 1
    )
) else (
    echo Reusing existing .venv environment.
)

call .venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo ERROR: Failed to activate .venv.
    exit /b 1
)

echo Upgrading pip tooling ...
python -m pip install --upgrade pip setuptools wheel
if %errorlevel% neq 0 (
    echo ERROR: Failed to upgrade pip tooling.
    exit /b 1
)

echo Installing backend dependencies ...
pip install -r backend\requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install backend dependencies.
    exit /b 1
)

echo Installing Next.js frontend dependencies ...
pushd frontend
npm install
if %errorlevel% neq 0 (
    popd
    echo ERROR: Failed to install Next.js frontend dependencies.
    exit /b 1
)
popd

if not exist ".env" (
    copy .env.example .env >nul
    echo Created .env from .env.example. Update it with your real credentials.
) else (
    echo .env already exists.
)

echo.
echo Setup complete.
echo.
echo Start backend:
echo   .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
echo Start frontend (new terminal):
echo   cd frontend ^&^& npm run dev
echo.
