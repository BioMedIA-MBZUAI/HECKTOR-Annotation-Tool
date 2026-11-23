@echo off
echo ================================================================
echo             HECKTOR Viewer - Environment Setup
echo ================================================================
echo.
echo This script will:
echo 1. Check if Python is installed
echo 2. Create a virtual environment
echo 3. Install all required packages (step by step)
echo.

REM Choose which Python command to use (python or py -3)
set "PY_CMD=python"

REM Check if Python is installed (standard python.exe on PATH)
echo Checking Python installation...
python --version >nul 2>&1
if not errorlevel 1 goto :python_ok

REM If python.exe is not found, try the Python launcher (py -3)
py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=py -3"
    goto :python_ok
)

REM Neither python nor py -3 found -> install Python
goto :install_python

:install_python
echo.
echo Python is not installed or not in PATH.
echo Attempting automatic installation of Python 3.9.13 (64-bit)...
echo.

REM URL of the official Python 3.9.13 64-bit installer
set "PYTHON_URL=https://www.python.org/ftp/python/3.9.13/python-3.9.13-amd64.exe"
set "PYTHON_INSTALLER=%TEMP%\python_installer_3_9_13.exe"

REM Download installer using PowerShell
echo Downloading Python installer...
powershell -Command "Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%' -UseBasicParsing"
if errorlevel 1 (
    echo.
    echo ERROR: Failed to download Python installer.
    echo Please install Python manually from: https://www.python.org/downloads/
    echo Make sure to check \"Add Python to PATH\" during installation.
    echo.
    pause
    exit /b 1
)

REM Run installer silently: install for all users, add to PATH, and install launcher
echo Running Python installer silently (this may take a few minutes)...
"%PYTHON_INSTALLER%" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 InstallLauncherAllUsers=1
if errorlevel 1 (
    echo.
    echo ERROR: Python installation failed.
    echo Please install Python manually from: https://www.python.org/downloads/
    echo Make sure to check \"Add Python to PATH\" during installation.
    echo.
    pause
    exit /b 1
)

REM Clean up installer
del "%PYTHON_INSTALLER%" >nul 2>&1

echo.
echo Python installation completed.
echo Verifying new Python installation using the launcher...
echo.

REM Prefer the Python launcher (works in the same session after install)
set "PY_CMD="
py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=py -3"
) else (
    python --version >nul 2>&1
    if not errorlevel 1 (
        set "PY_CMD=python"
    )
)

if not defined PY_CMD (
    echo ERROR: Could not detect Python even after installation.
    echo You may need to restart your computer and run this script again.
    echo.
    pause
    exit /b 1
)

echo Detected Python command: %PY_CMD%
echo.
goto :python_ok

:python_ok
echo  Python is installed
%PY_CMD% --version

REM Create virtual environment
echo.
echo Creating virtual environment...
if exist "hecktor_env" (
    echo Virtual environment already exists. Removing old one...
    rmdir /s /q hecktor_env
)

%PY_CMD% -m venv hecktor_env
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment!
    pause
    exit /b 1
)

echo  Virtual environment created

REM Activate virtual environment
echo.
echo Activating virtual environment...
call hecktor_env\Scripts\activate.bat

REM Upgrade pip first (separately)
echo.
echo Step 1: Upgrading pip...
%PY_CMD% -m pip install --upgrade pip
if errorlevel 1 (
    echo Warning: Pip upgrade failed, but continuing...
)

REM Install packages one by one to avoid conflicts
echo.
echo Step 2: Installing core packages...
echo Installing NumPy...
pip install numpy
if errorlevel 1 goto :install_error

echo Installing SciPy...
pip install scipy
if errorlevel 1 goto :install_error

echo Installing scikit-image...
pip install scikit-image
if errorlevel 1 goto :install_error

echo Installing nibabel...
pip install nibabel
if errorlevel 1 goto :install_error

echo.
echo Step 3: Installing GUI packages...
echo Installing PyQt5...
pip install PyQt5
if errorlevel 1 goto :install_error

echo Installing napari (this may take a few minutes)...
pip install napari
if errorlevel 1 goto :install_error

echo.
echo Step 4: Verifying installation...

REM Use the virtual environment's python (after activation) for all checks
python -c "import numpy; print(' NumPy works')" 2>nul
if errorlevel 1 echo NumPy failed

python -c "import scipy; print(' SciPy works')" 2>nul
if errorlevel 1 echo SciPy failed

python -c "import skimage; print(' scikit-image works')" 2>nul
if errorlevel 1 echo scikit-image failed

python -c "import nibabel; print(' nibabel works')" 2>nul
if errorlevel 1 echo nibabel failed

python -c "import PyQt5; print(' PyQt5 works')" 2>nul
if errorlevel 1 echo PyQt5 failed

python -c "import napari; print(' napari works')" 2>nul
if errorlevel 1 echo napari failed

echo.
echo ================================================================
echo                      INSTALLATION COMPLETE!  
echo ================================================================
echo.
echo  Virtual environment created: hecktor_env
echo  All required packages installed
echo.
echo 📋 Next steps:
echo 1. Edit 'run_hecktor.bat' to set your data folder path
echo 2. Double-click 'run_hecktor.bat' to start the annotation tool
echo.
echo The virtual environment is located in: %CD%\hecktor_env
echo.
echo If you see any  failed messages above, contact technical support.
echo.
pause
goto :end

:install_error
echo.
echo ERROR: Failed to install packages!
echo.
echo Try these solutions:
echo 1. Close this window and run as administrator:
echo    Right-click setup_environment.bat → "Run as administrator"
echo.
echo 2. Check your internet connection
echo.
echo 3. Try manual installation:
echo    - Open Command Prompt as administrator
echo    - Navigate to this folder
echo    - Run: hecktor_env\Scripts\activate
echo    - Run: pip install numpy scipy scikit-image nibabel PyQt5 "napari[all]"
echo.
pause
exit /b 1

:end
echo Setup completed successfully!