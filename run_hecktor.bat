@echo off
echo Starting HECKTOR Annotation Tool...
echo.

REM Check if virtual environment exists
if not exist "hecktor_env\Scripts\activate.bat" (
    echo Error: Virtual environment not found!
    echo Please run 'setup_environment.bat' first to set up the environment.
    echo.
    pause
    exit /b 1
)

REM Check if main script exists
if not exist "hecktor_viewer.py" (
    echo Error: hecktor_viewer.py not found!
    echo Make sure this launcher is in the same folder as the Python script.
    echo.
    pause
    exit /b 1
)

REM Activate virtual environment
echo Activating virtual environment...
call hecktor_env\Scripts\activate.bat

REM Data folder: first argument, else HECKTOR_DATA, else ask
set "DATA_DIR=%~1"
if "%DATA_DIR%"=="" set "DATA_DIR=%HECKTOR_DATA%"
if "%DATA_DIR%"=="" set /p "DATA_DIR=Enter the path to your local data folder: "
echo.

REM Run the HECKTOR viewer
echo Loading HECKTOR Viewer with data from "%DATA_DIR%"
echo.
python hecktor_viewer.py --data "%DATA_DIR%"

REM Keep window open if there's an error
if errorlevel 1 (
    echo.
    echo An error occurred. Press any key to close.
    pause
)
