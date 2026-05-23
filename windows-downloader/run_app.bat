@echo off
setlocal enabledelayedexpansion

REM ═══════════════════════════════════════════════
REM COLORS AND FORMATTING
REM ═══════════════════════════════════════════════

for /F "tokens=1,2 delims=#" %%a in ('"prompt #$H#$E# & echo on & for %%b in (1) do rem"') do (
  set "DEL=%%a"
  set "COLOR_GREEN=%%b[32m"
  set "COLOR_YELLOW=%%b[33m"
  set "COLOR_RED=%%b[31m"
  set "COLOR_CYAN=%%b[36m"
  set "COLOR_RESET=%%b[0m"
)

set "LABEL_OK=%COLOR_GREEN%[OK]%COLOR_RESET%"
set "LABEL_WARN=%COLOR_YELLOW%[!!]%COLOR_RESET%"
set "LABEL_ERR=%COLOR_RED%[XX]%COLOR_RESET%"
set "LABEL_INFO=%COLOR_CYAN%[..]%COLOR_RESET%"

REM ═══════════════════════════════════════════════
REM GET SCRIPT DIRECTORY
REM ═══════════════════════════════════════════════

cd /d "%~dp0"

echo %LABEL_INFO% Pro YouTube Downloader - Windows Launcher
echo %LABEL_INFO% =========================================
echo.

REM ═══════════════════════════════════════════════
REM DETECT ARCHITECTURE
REM ═══════════════════════════════════════════════

echo %LABEL_INFO% Detecting system architecture...

wmic os get OSArchitecture | findstr /i "ARM" >nul 2>&1
if %errorlevel% equ 0 (
    echo %LABEL_OK% Architecture: ARM64
    set "ARCH=arm64"
) else (
    echo %LABEL_OK% Architecture: x86_64
    set "ARCH=x86_64"
)

echo.

REM ═══════════════════════════════════════════════
REM CHECK PYTHON
REM ═══════════════════════════════════════════════

echo %LABEL_INFO% Checking Python installation...

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo %LABEL_WARN% Python not found!
    echo.
    echo %LABEL_INFO% Please install Python from https://python.org
    echo %LABEL_INFO% OR use winget: winget install Python.Python.3
    echo.
    echo %LABEL_WARN% After installing Python, please re-run this script.
    echo.
    pause
    exit /b 1
) else (
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do set "PYTHON_VER=%%i"
    echo %LABEL_OK% Python %PYTHON_VER% found
)

echo.

REM ═══════════════════════════════════════════════
REM CHECK FFMPEG
REM ═══════════════════════════════════════════════

echo %LABEL_INFO% Checking FFmpeg installation...

ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo %LABEL_WARN% FFmpeg not found!
    echo.
    echo %LABEL_INFO% Please install FFmpeg using one of these methods:
    echo.
    echo   Method 1 - Scoop ^(recommended^):
    echo     scoop install ffmpeg
    echo.
    echo   Method 2 - Chocolatey:
    echo     choco install ffmpeg
    echo.
    echo   Method 3 - winget:
    echo     winget install Gyan.FFmpeg
    echo.
    echo %LABEL_WARN% After installing FFmpeg, please re-run this script.
    echo.
    
    REM Check if Scoop is available
    where scoop >nul 2>&1
    if %errorlevel% equ 0 (
        echo %LABEL_INFO% Scoop detected. Would you like to install FFmpeg now? ^(Y/N^)
        set /p INSTALL_FFMPEG="> "
        if /i "!INSTALL_FFMPEG!"=="Y" (
            echo %LABEL_INFO% Installing FFmpeg with Scoop...
            scoop install ffmpeg
            if %errorlevel% equ 0 (
                echo %LABEL_OK% FFmpeg installed successfully!
            ) else (
                echo %LABEL_ERR% Failed to install FFmpeg. Please install manually.
            )
        )
    ) else (
        REM Check if Chocolatey is available
        where choco >nul 2>&1
        if %errorlevel% equ 0 (
            echo %LABEL_INFO% Chocolatey detected. Would you like to install FFmpeg now? ^(Y/N^)
            set /p INSTALL_FFMPEG="> "
            if /i "!INSTALL_FFMPEG!"=="Y" (
                echo %LABEL_INFO% Installing FFmpeg with Chocolatey...
                choco install ffmpeg -y
                if %errorlevel% equ 0 (
                    echo %LABEL_OK% FFmpeg installed successfully!
                ) else (
                    echo %LABEL_ERR% Failed to install FFmpeg. Please install manually.
                )
            )
        )
    )
    
    echo.
    echo %LABEL_WARN% Please close and re-run this script after installing FFmpeg.
    pause
    exit /b 1
) else (
    for /f "tokens=3" %%i in ('ffmpeg -version 2^>^&1 ^| findstr /i "ffmpeg version"') do set "FFMPEG_VER=%%i"
    echo %LABEL_OK% FFmpeg %FFMPEG_VER% found
)

echo.

REM ═══════════════════════════════════════════════
REM CHECK HARDWARE ENCODER
REM ═══════════════════════════════════════════════

echo %LABEL_INFO% Checking hardware encoders...

ffmpeg -hide_banner -encoders 2>nul | findstr "hevc_nvenc" >nul 2>&1
if %errorlevel% equ 0 (
    echo %LABEL_OK% NVIDIA NVENC encoder detected ^(GPU acceleration^)
    set "ENCODER=GPU (NVIDIA NVENC)"
    goto :encoder_found
)

ffmpeg -hide_banner -encoders 2>nul | findstr "hevc_amf" >nul 2>&1
if %errorlevel% equ 0 (
    echo %LABEL_OK% AMD AMF encoder detected ^(GPU acceleration^)
    set "ENCODER=GPU (AMD AMF)"
    goto :encoder_found
)

ffmpeg -hide_banner -encoders 2>nul | findstr "hevc_qsv" >nul 2>&1
if %errorlevel% equ 0 (
    echo %LABEL_OK% Intel QSV encoder detected ^(GPU acceleration^)
    set "ENCODER=GPU (Intel QSV)"
    goto :encoder_found
)

echo %LABEL_WARN% No hardware encoder found. Will use software encoding (libx265).
set "ENCODER=CPU (libx265)"

:encoder_found
echo.

REM ═══════════════════════════════════════════════
REM CREATE VIRTUAL ENVIRONMENT
REM ═══════════════════════════════════════════════

echo %LABEL_INFO% Setting up Python virtual environment...

if not exist ".venv" (
    echo %LABEL_INFO% Creating virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo %LABEL_ERR% Failed to create virtual environment!
        pause
        exit /b 1
    )
    echo %LABEL_OK% Virtual environment created
) else (
    echo %LABEL_OK% Virtual environment already exists
)

echo.

REM ═══════════════════════════════════════════════
REM ACTIVATE VIRTUAL ENVIRONMENT
REM ═══════════════════════════════════════════════

echo %LABEL_INFO% Activating virtual environment...

call .venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo %LABEL_ERR% Failed to activate virtual environment!
    pause
    exit /b 1
)

echo %LABEL_OK% Virtual environment activated

echo.

REM ═══════════════════════════════════════════════
REM INSTALL PYTHON LIBRARIES
REM ═══════════════════════════════════════════════

echo %LABEL_INFO% Installing Python packages...

pip show yt-dlp >nul 2>&1
if %errorlevel% neq 0 (
    echo %LABEL_INFO% Installing yt-dlp...
    pip install -q -U yt-dlp
    if %errorlevel% equ 0 (
        echo %LABEL_OK% yt-dlp installed
    ) else (
        echo %LABEL_ERR% Failed to install yt-dlp
    )
) else (
    echo %LABEL_OK% yt-dlp already installed
)

pip show streamlit >nul 2>&1
if %errorlevel% neq 0 (
    echo %LABEL_INFO% Installing streamlit...
    pip install -q -U streamlit
    if %errorlevel% equ 0 (
        echo %LABEL_OK% streamlit installed
    ) else (
        echo %LABEL_ERR% Failed to install streamlit
    )
) else (
    echo %LABEL_OK% streamlit already installed
)

echo.

REM ═══════════════════════════════════════════════
REM LAUNCH APP
REM ═══════════════════════════════════════════════

echo %LABEL_INFO% Starting Pro YouTube Downloader...
echo.
echo %LABEL_INFO% The app will open in your default browser at:
echo %LABEL_INFO% http://localhost:8501
echo.
echo %LABEL_INFO% Press Ctrl+C to stop the server.
echo.

REM Wait 3 seconds before opening browser
timeout /t 3 /nobreak >nul

REM Open browser in background
start "" http://localhost:8501

REM Launch Streamlit
streamlit run app.py

endlocal
