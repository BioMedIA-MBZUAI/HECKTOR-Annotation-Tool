@echo off
echo ================================================================
echo              HECKTOR Viewer - Installation Check
echo ================================================================
echo.

REM Check if virtual environment exists
if not exist "hecktor_env\Scripts\activate.bat" (
    echo ❌ Virtual environment not found!
    echo Please run 'setup_environment.bat' first.
    echo.
    goto :end
)

echo ✅ Virtual environment found
echo.

REM Activate virtual environment
echo Activating virtual environment...
call hecktor_env\Scripts\activate.bat

echo.
echo 🧪 Testing Python packages...
echo.

REM Test each package individually
echo Testing NumPy...
python -c "import numpy; print('✅ NumPy version:', numpy.__version__)" 2>nul
if errorlevel 1 echo ❌ NumPy import failed!

echo Testing SciPy...
python -c "import scipy; print('✅ SciPy version:', scipy.__version__)" 2>nul
if errorlevel 1 echo ❌ SciPy import failed!

echo Testing scikit-image...
python -c "import skimage; print('✅ scikit-image version:', skimage.__version__)" 2>nul
if errorlevel 1 echo ❌ scikit-image import failed!

echo Testing SimpleITK...
python -c "import SimpleITK; print('✅ SimpleITK version:', SimpleITK.Version_VersionString())" 2>nul
if errorlevel 1 echo ❌ SimpleITK import failed!

echo Testing PyQt5...
python -c "import PyQt5.QtWidgets; print('✅ PyQt5 works!')" 2>nul
if errorlevel 1 echo ❌ PyQt5 import failed!

echo Testing napari...
python -c "import napari; print('✅ napari version:', napari.__version__)" 2>nul
if errorlevel 1 echo ❌ napari import failed!

echo.
echo 🧪 Testing main script...
if exist "hecktor_viewer.py" (
    echo ✅ hecktor_viewer.py found
    python hecktor_viewer.py --help >nul 2>&1
    if errorlevel 1 (
        echo ❌ Script has import errors
    ) else (
        echo ✅ Script imports successfully
    )
) else (
    echo ❌ hecktor_viewer.py not found!
)

echo.
echo 📂 Checking file structure...
if exist "run_hecktor.bat" (
    echo ✅ run_hecktor.bat found
) else (
    echo ❌ run_hecktor.bat not found!
)

if exist "requirements.txt" (
    echo ✅ requirements.txt found
) else (
    echo ⚠️  requirements.txt not found (optional)
)

echo.
echo ================================================================
echo                      Summary
echo ================================================================
echo.
echo If all tests show ✅, your installation is ready!
echo.
echo 📋 To use the viewer:
echo 1. Edit 'run_hecktor.bat' to set your data folder path
echo 2. Double-click 'run_hecktor.bat' to start
echo.
echo If you see any ❌ errors:
echo 1. Try running 'setup_environment.bat' again
echo 2. Run setup as administrator
echo 3. Check the troubleshooting guide
echo.

:end
pause