#!/bin/bash
# Change to the directory where this script is located
cd "$(dirname "$0")"
echo "Starting HECKTOR Annotation Tool..."
echo ""

# Check if virtual environment exists
if [ ! -f "hecktor_env/bin/activate" ]; then
    echo "Error: Virtual environment not found!"
    echo "Please run 'setup_environment_mac.command' first to set up the environment."
    echo ""
    read -p "Press any key to continue..."
    exit 1
fi

# Check if main script exists
if [ ! -f "hecktor_viewer.py" ]; then
    echo "Error: hecktor_viewer.py not found!"
    echo "Make sure this launcher is in the same folder as the Python script."
    echo ""
    read -p "Press any key to continue..."
    exit 1
fi

# Activate virtual environment
echo "Activating virtual environment..."
source hecktor_env/bin/activate

# Data folder: first argument, else HECKTOR_DATA, else ask
DATA_DIR="${1:-$HECKTOR_DATA}"
if [ -z "$DATA_DIR" ]; then
    read -r -p "Enter the path to your local data folder: " DATA_DIR
fi
echo ""

# Run the HECKTOR viewer
echo "Loading HECKTOR Viewer with data from: $DATA_DIR"
echo ""
python3 hecktor_viewer.py --data "$DATA_DIR"

# Keep window open if there's an error
if [ $? -ne 0 ]; then
    echo ""
    echo "An error occurred. Press any key to close."
    read -p "Press any key to continue..."
fi
