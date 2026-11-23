#!/bin/bash
# Helper script to make all .command files executable
# Change to the directory where this script is located
cd "$(dirname "$0")"

echo "Making all .command files executable..."
echo ""

# Make this script executable first (in case it wasn't)
chmod +x "$0" 2>/dev/null

# Find and make all .command files executable
for file in *.command; do
    if [ -f "$file" ]; then
        chmod +x "$file"
        echo "✓ Made executable: $file"
    fi
done

echo ""
echo "Done! All .command files are now executable."
echo ""
echo "You can now double-click:"
echo "  - setup_environment_mac.command (first time setup)"
echo "  - run_hecktor_mac.command (to run the tool)"
echo ""
read -p "Press any key to close..."

