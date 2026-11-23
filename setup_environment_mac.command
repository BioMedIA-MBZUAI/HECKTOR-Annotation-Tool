#!/bin/bash
# Change to the directory where this script is located
cd "$(dirname "$0")"
echo "================================================================"
echo "             HECKTOR Viewer - Environment Setup"
echo "================================================================"
echo ""
echo "This script will:"
echo "1. Check if Python is installed"
echo "2. Create a virtual environment"
echo "3. Install all required packages (step by step)"
echo ""

# Choose which Python command to use (python3 or python)
PY_CMD=""

# Target Python version to check for (change this to test different versions)
REQUIRED_PYTHON_VERSION="3.11"
REQUIRED_MAJOR_MINOR="3.11"

# TEST MODE: Set to true to force installation path (ignores existing Python)
# This is useful for testing the download/installation logic
FORCE_INSTALL_TEST=false

# Check if Python is installed with the required version
echo "Checking Python installation..."
echo "Looking for Python $REQUIRED_PYTHON_VERSION or compatible version..."

# Function to check Python version
check_python_version() {
    local python_cmd=$1
    if command -v "$python_cmd" &> /dev/null; then
        local version=$($python_cmd --version 2>&1 | awk '{print $2}')
        local major_minor=$(echo "$version" | cut -d. -f1,2)
        # Check if version matches or is newer (3.11.x, 3.12.x, etc. for 3.11 requirement)
        # Compare version numbers properly
        local required_major=$(echo "$REQUIRED_MAJOR_MINOR" | cut -d. -f1)
        local required_minor=$(echo "$REQUIRED_MAJOR_MINOR" | cut -d. -f2)
        local found_major=$(echo "$major_minor" | cut -d. -f1)
        local found_minor=$(echo "$major_minor" | cut -d. -f2)
        
        if [ "$found_major" -gt "$required_major" ] || \
           ([ "$found_major" -eq "$required_major" ] && [ "$found_minor" -ge "$required_minor" ]); then
            return 0
        fi
    fi
    return 1
}

# Check for Python 3.11 specifically first (skip if FORCE_INSTALL_TEST is true)
if [ "$FORCE_INSTALL_TEST" = true ]; then
    echo "TEST MODE: Forcing installation path (ignoring existing Python)"
    # Force empty PY_CMD to trigger installation path
    PY_CMD=""
elif command -v python3.11 &> /dev/null; then
    PY_CMD="python3.11"
    echo "Found python3.11"
elif check_python_version "python3"; then
    PY_CMD="python3"
    echo "Found compatible python3: $(python3 --version 2>&1)"
elif check_python_version "python"; then
    PY_CMD="python"
    echo "Found compatible python: $(python --version 2>&1)"
fi

# If PY_CMD is still empty, trigger installation
if [ -z "$PY_CMD" ]; then
    echo ""
    echo "Python $REQUIRED_PYTHON_VERSION (or compatible) is not installed or not in PATH."
    echo "Attempting automatic installation..."
    echo ""
    
    # Skip Homebrew for testing - go directly to manual installation
    # Uncomment the Homebrew section below if you want to use it
    USE_HOMEBREW=false
    
    # Check if Homebrew is installed (only if USE_HOMEBREW is true)
    if [ "$USE_HOMEBREW" = true ] && command -v brew &> /dev/null; then
        echo "Homebrew detected. Installing Python 3 via Homebrew..."
        echo "This may take a few minutes..."
        brew install python3
        if [ $? -eq 0 ]; then
            echo ""
            echo "Python installation completed via Homebrew."
            # Refresh PATH to find newly installed python3
            export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
            if command -v python3 &> /dev/null; then
                PY_CMD="python3"
            else
                echo "Warning: Python installed but not found in PATH."
                echo "You may need to restart Terminal or run: export PATH=\"/usr/local/bin:/opt/homebrew/bin:\$PATH\""
                read -p "Press any key to continue..."
                exit 1
            fi
        else
            echo ""
            echo "ERROR: Failed to install Python via Homebrew."
            echo "Please install Python manually:"
            echo "  - Run: brew install python3"
            echo "  - Or download from: https://www.python.org/downloads/"
            echo ""
            read -p "Press any key to continue..."
            exit 1
        fi
    else
        # Homebrew disabled or not installed - download Python installer directly
        if [ "$USE_HOMEBREW" = false ]; then
            echo "Using direct Python installer download (Homebrew disabled for testing)..."
        else
            echo "Homebrew not found. Downloading Python installer..."
        fi
        echo ""
        
        # Detect macOS architecture
        ARCH=$(uname -m)
        if [ "$ARCH" = "arm64" ]; then
            PYTHON_URL="https://www.python.org/ftp/python/3.11.7/python-3.11.7-macos11.pkg"
            PYTHON_INSTALLER="$HOME/Downloads/python-3.11.7-macos11.pkg"
        else
            PYTHON_URL="https://www.python.org/ftp/python/3.11.7/python-3.11.7-macosx10.9.pkg"
            PYTHON_INSTALLER="$HOME/Downloads/python-3.11.7-macosx10.9.pkg"
        fi
        
        echo "Downloading Python installer to Downloads folder..."
        curl -L -o "$PYTHON_INSTALLER" "$PYTHON_URL"
        
        if [ $? -eq 0 ] && [ -f "$PYTHON_INSTALLER" ]; then
            echo ""
            echo "Python installer downloaded successfully."
            echo ""
            
            # Try to install silently using installer command (requires admin)
            echo "Attempting automatic installation..."
            echo "This may require your password for administrator privileges."
            echo ""
            
            # Install silently using installer command
            sudo installer -pkg "$PYTHON_INSTALLER" -target /
            
            if [ $? -eq 0 ]; then
                echo ""
                echo "✓ Python installed successfully!"
                echo ""
                
                # Wait a moment for installation to complete
                sleep 2
                
                # Refresh PATH to find newly installed Python
                export PATH="/Library/Frameworks/Python.framework/Versions/3.11/bin:/usr/local/bin:$PATH"
                
                # Check for Python in common installation locations
                PYTHON_PATHS=(
                    "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"
                    "/usr/local/bin/python3"
                    "/usr/bin/python3"
                )
                
                for python_path in "${PYTHON_PATHS[@]}"; do
                    if [ -f "$python_path" ]; then
                        PY_CMD="$python_path"
                        echo "Found Python: $PY_CMD"
                        break
                    fi
                done
                
                # Also check if python3 is now in PATH
                if [ -z "$PY_CMD" ] && command -v python3 &> /dev/null; then
                    PY_CMD="python3"
                    echo "Found Python: $(command -v python3)"
                fi
                
                if [ -z "$PY_CMD" ]; then
                    echo ""
                    echo "Warning: Python installed but not found in PATH."
                    echo "Trying to locate Python installation..."
                    # Try to find it
                    if [ -f "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3" ]; then
                        PY_CMD="/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"
                        export PATH="/Library/Frameworks/Python.framework/Versions/3.11/bin:$PATH"
                        echo "Using: $PY_CMD"
                    else
                        echo "ERROR: Could not locate installed Python."
                        echo "Please run this script again, or add Python to your PATH."
                        read -p "Press any key to exit..."
                        exit 1
                    fi
                fi
                
                echo ""
                echo "Continuing with setup..."
                echo ""
            else
                # Silent installation failed or was cancelled - try GUI installation with auto-wait
                echo ""
                echo "Silent installation not available or was cancelled."
                echo "Opening installer GUI... Please complete the installation."
                echo ""
                echo "This script will automatically continue once Python is detected..."
                echo ""
                
                open "$PYTHON_INSTALLER"
                
                # Wait for Python to be installed (poll for up to 5 minutes)
                echo "Waiting for Python installation to complete..."
                MAX_WAIT=300  # 5 minutes
                WAIT_INTERVAL=5  # Check every 5 seconds
                ELAPSED=0
                
                while [ $ELAPSED -lt $MAX_WAIT ]; do
                    # Check common Python installation locations
                    if [ -f "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3" ] || \
                       command -v python3 &> /dev/null; then
                        echo ""
                        echo "✓ Python installation detected!"
                        echo ""
                        
                        # Set PY_CMD
                        if [ -f "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3" ]; then
                            PY_CMD="/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"
                            export PATH="/Library/Frameworks/Python.framework/Versions/3.11/bin:$PATH"
                        elif command -v python3 &> /dev/null; then
                            PY_CMD="python3"
                        fi
                        
                        break
                    fi
                    
                    sleep $WAIT_INTERVAL
                    ELAPSED=$((ELAPSED + WAIT_INTERVAL))
                    echo -n "."
                done
                
                if [ -z "$PY_CMD" ]; then
                    echo ""
                    echo ""
                    echo "ERROR: Python installation not detected after waiting."
                    echo "Please make sure Python installation completed successfully."
                    echo "Then run this script again."
                    read -p "Press any key to exit..."
                    exit 1
                fi
            fi
        else
            echo ""
            echo "ERROR: Failed to download Python installer."
            echo "Please install Python manually:"
            echo "  - Install Homebrew first: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
            echo "  - Then run: brew install python3"
            echo "  - Or download from: https://www.python.org/downloads/"
            echo ""
            read -p "Press any key to continue..."
            exit 1
        fi
    fi
fi

echo "✓ Python is installed"
$PY_CMD --version

# Create virtual environment
echo ""
echo "Creating virtual environment..."
if [ -d "hecktor_env" ]; then
    echo "Virtual environment already exists. Removing old one..."
    rm -rf hecktor_env
fi

$PY_CMD -m venv hecktor_env
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to create virtual environment!"
    read -p "Press any key to continue..."
    exit 1
fi

echo "✓ Virtual environment created"

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source hecktor_env/bin/activate

# Upgrade pip first (separately)
echo ""
echo "Step 1: Upgrading pip..."
$PY_CMD -m pip install --upgrade pip
if [ $? -ne 0 ]; then
    echo "Warning: Pip upgrade failed, but continuing..."
fi

# Install packages one by one to avoid conflicts
echo ""
echo "Step 2: Installing core packages..."
echo "Installing NumPy..."
pip install numpy
if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Failed to install packages!"
    echo ""
    echo "Try these solutions:"
    echo "1. Check your internet connection"
    echo ""
    echo "2. Try manual installation:"
    echo "   - Open Terminal"
    echo "   - Navigate to this folder"
    echo "   - Run: source hecktor_env/bin/activate"
    echo "   - Run: pip install numpy scipy scikit-image nibabel PyQt5 \"napari[all]\""
    echo ""
    read -p "Press any key to continue..."
    exit 1
fi

echo "Installing SciPy..."
pip install scipy
if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Failed to install packages!"
    echo ""
    echo "Try these solutions:"
    echo "1. Check your internet connection"
    echo ""
    echo "2. Try manual installation:"
    echo "   - Open Terminal"
    echo "   - Navigate to this folder"
    echo "   - Run: source hecktor_env/bin/activate"
    echo "   - Run: pip install numpy scipy scikit-image nibabel PyQt5 \"napari[all]\""
    echo ""
    read -p "Press any key to continue..."
    exit 1
fi

echo "Installing scikit-image..."
pip install scikit-image
if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Failed to install packages!"
    echo ""
    echo "Try these solutions:"
    echo "1. Check your internet connection"
    echo ""
    echo "2. Try manual installation:"
    echo "   - Open Terminal"
    echo "   - Navigate to this folder"
    echo "   - Run: source hecktor_env/bin/activate"
    echo "   - Run: pip install numpy scipy scikit-image nibabel PyQt5 \"napari[all]\""
    echo ""
    read -p "Press any key to continue..."
    exit 1
fi

echo "Installing nibabel..."
pip install nibabel
if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Failed to install packages!"
    echo ""
    echo "Try these solutions:"
    echo "1. Check your internet connection"
    echo ""
    echo "2. Try manual installation:"
    echo "   - Open Terminal"
    echo "   - Navigate to this folder"
    echo "   - Run: source hecktor_env/bin/activate"
    echo "   - Run: pip install numpy scipy scikit-image nibabel PyQt5 \"napari[all]\""
    echo ""
    read -p "Press any key to continue..."
    exit 1
fi

echo ""
echo "Step 3: Installing GUI packages..."
echo "Installing PyQt5..."
pip install PyQt5
if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Failed to install packages!"
    echo ""
    echo "Try these solutions:"
    echo "1. Check your internet connection"
    echo ""
    echo "2. Try manual installation:"
    echo "   - Open Terminal"
    echo "   - Navigate to this folder"
    echo "   - Run: source hecktor_env/bin/activate"
    echo "   - Run: pip install numpy scipy scikit-image nibabel PyQt5 \"napari[all]\""
    echo ""
    read -p "Press any key to continue..."
    exit 1
fi

echo "Installing napari (this may take a few minutes)..."
pip install napari
if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Failed to install packages!"
    echo ""
    echo "Try these solutions:"
    echo "1. Check your internet connection"
    echo ""
    echo "2. Try manual installation:"
    echo "   - Open Terminal"
    echo "   - Navigate to this folder"
    echo "   - Run: source hecktor_env/bin/activate"
    echo "   - Run: pip install numpy scipy scikit-image nibabel PyQt5 \"napari[all]\""
    echo ""
    read -p "Press any key to continue..."
    exit 1
fi

echo ""
echo "Step 4: Verifying installation..."

# Use the virtual environment's python (after activation) for all checks
python3 -c "import numpy; print('✓ NumPy works')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "✗ NumPy failed"
fi

python3 -c "import scipy; print('✓ SciPy works')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "✗ SciPy failed"
fi

python3 -c "import skimage; print('✓ scikit-image works')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "✗ scikit-image failed"
fi

python3 -c "import nibabel; print('✓ nibabel works')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "✗ nibabel failed"
fi

python3 -c "import PyQt5; print('✓ PyQt5 works')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "✗ PyQt5 failed"
fi

python3 -c "import napari; print('✓ napari works')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "✗ napari failed"
fi

echo ""
echo "================================================================"
echo "                      INSTALLATION COMPLETE!"
echo "================================================================"
echo ""
echo "✓ Virtual environment created: hecktor_env"
echo "✓ All required packages installed"
echo ""
echo "📋 Next steps:"
echo "1. Edit 'run_hecktor_mac.sh' to set your data folder path"
echo "2. Run 'chmod +x run_hecktor_mac.sh' to make it executable"
echo "3. Run './run_hecktor_mac.sh' to start the annotation tool"
echo ""
echo "The virtual environment is located in: $(pwd)/hecktor_env"
echo ""
echo "If you see any ✗ failed messages above, contact technical support."
echo ""
read -p "Press any key to continue..."
echo ""
echo "Setup completed successfully!"

