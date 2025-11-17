#!/bin/bash

# Navigate to the script's directory
cd "$(dirname "$0")"

# Clean up any leftover temporary files from previous runs
rm -f open_chrome.ps1 restart_after_update.sh delayed_start.sh 2>/dev/null

# Fan Finder - Mac Startup Script (Double-click to run)
echo "========================================="
echo "    FAN FINDER - STARTING UP"
echo "========================================="
echo
echo "AI Assistant integrated for installation help"
echo "   AI can provide guidance and assistance with your permission"

# Check if Python is installed and working
echo "Checking Python installation..."

# Quick system compatibility check
echo
echo "🛡️  Checking system compatibility..."
python3 -c "
import sys
sys.path.append('app')
try:
    from ai_helper import create_ai_helper
    helper = create_ai_helper()
    if helper:
        compatibility = helper.get_system_compatibility_check()
        print(f'✅ COMPATIBILITY: {compatibility[\"compatible\"]}')
        if compatibility['issues'] != 'None detected':
            print(f'⚠️  ISSUES: {compatibility[\"issues\"]}')
        print(f'📋 RECOMMENDATIONS: {compatibility[\"recommendations\"]}')
    else:
        print('✅ System check complete')
except Exception as e:
    print('✅ System check complete - proceeding with installation')
" 2>/dev/null || echo "✅ System check complete"
echo

PYTHON_CMD=""
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo
    echo "❌ Python not found! Installing automatically..."
    echo
    echo "🤖 Consulting AI Assistant for installation guidance..."
    python3 -c "import sys; sys.path.append('app'); from ai_helper import create_ai_helper; helper = create_ai_helper(); print(helper.get_installation_guidance('Python Installation', 'Python not found on macOS') if helper else 'AI Assistant unavailable - proceeding with standard installation')" 2>/dev/null || true
    echo
    echo "🍎 Installing Python via Homebrew..."
    echo "This may take a few minutes..."
    echo
    
    # Check if Homebrew is installed
    if ! command -v brew &> /dev/null; then
        echo "📦 Installing Homebrew first..."
        echo
        echo "⚠️  IMPORTANT: You may be asked for your password to install Homebrew"
        echo "    This is normal - please enter your Mac login password when prompted"
        echo "    If nothing happens, check if the Terminal is asking for your password below"
        echo
        
        # Bring terminal to front during installation
        osascript -e 'tell application "Terminal" to activate'
        
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        
        # Add Homebrew to PATH for this session
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
    
    echo "📦 Installing Python..."
    echo
    echo "⚠️  IMPORTANT: You may be asked for your password to install Python"
    echo "    This is normal - please enter your Mac login password when prompted"
    echo "    If nothing happens, check if the Terminal is asking for your password below"
    echo
    
    # Bring terminal to front during Python installation
    osascript -e 'tell application "Terminal" to activate'
    
    brew install python3
    PYTHON_CMD="python3"
    
    if ! command -v $PYTHON_CMD &> /dev/null; then
        echo "❌ Python installation failed"
        echo
        echo "📋 Analyzing installation issue..."
        python3 -c "
import sys
sys.path.append('app')
try:
    from ai_helper import create_ai_helper
    helper = create_ai_helper()
    if helper:
        success, guidance = helper.suggest_installation_fix(
            'Python Installation Failed', 
            'Python installation via Homebrew failed on macOS', 
            'macOS Python installation'
        )
        print(guidance)
        
except Exception as e:
    print('Please try the following manual steps:')
    print('1. Restart Terminal and try again')
    print('2. Run: /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"')
    print('3. Then run: brew install python3')
    
print('Please follow the instructions above and try running the server again.')
" 2>/dev/null || echo "Please install Python manually and try again"
        
        read -p "Press Enter to exit..."
        exit 1
    fi
    
    echo "✅ Python installed successfully!"
    echo
fi

echo "✅ Python found: $PYTHON_CMD"
$PYTHON_CMD --version
echo

# Check if required packages are installed
echo "Checking required packages..."
if ! $PYTHON_CMD -c "import flask, flask_socketio, selenium, undetected_chromedriver, requests, firebase_admin" &>/dev/null; then
    echo
    echo "❌ Required packages not found! Installing automatically..."
    echo
    echo "📦 Installing Python packages..."
    echo "This may take 2-3 minutes..."
    
    # Install packages with pip
    $PYTHON_CMD -m pip install --upgrade pip --quiet
    $PYTHON_CMD -m pip install flask flask-socketio flask-cors selenium undetected-chromedriver requests python-dotenv psutil firebase-admin --quiet
    
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install some packages"
        echo
        echo "📋 Analyzing package installation failure..."
        $PYTHON_CMD -c "
import sys
sys.path.append('app')
try:
    from ai_helper import create_ai_helper
    helper = create_ai_helper()
    if helper:
        success, guidance = helper.suggest_installation_fix(
            'Package Installation Failed', 
            'pip install failed for required packages on macOS', 
            'macOS package installation'
        )
        print(guidance)
        
except Exception as e:
    print('Please try the following manual steps:')
    print('1. Update pip: python3 -m pip install --upgrade pip')
    print('2. Try installing packages individually')
    print('3. Check if Xcode command line tools are installed: xcode-select --install')
    
print('Please follow the instructions above to resolve package installation issues.')
" 2>/dev/null || echo "Trying with verbose output to see the error..."
        
        $PYTHON_CMD -m pip install flask flask-socketio flask-cors selenium undetected-chromedriver requests python-dotenv psutil firebase-admin
        read -p "Press Enter to exit..."
        exit 1
    fi
    
    echo "SUCCESS: All packages installed successfully!"
    echo
fi

echo "SUCCESS: All required packages found"
echo

echo "Setting up configuration..."
mkdir -p app/config
mkdir -p app/data
if [ -f "firebase-key.json" ]; then
    cp firebase-key.json app/config/firebase-key-13504509.json 2>/dev/null
fi

echo
echo "===================================="
echo "   ACCESS POINT:"
echo "   WEB INTERFACE: http://localhost:5000"
echo "   CHROME BROWSER: Will appear on your desktop"
echo "===================================="
echo

# Check if port 5000 is already in use
echo "Checking if Fan Finder is already running..."
if lsof -i :5000 >/dev/null 2>&1; then
    echo
    echo "⚠️  Port 5000 is already in use!"
    echo "Fan Finder may already be running."
    echo
    echo "If you want to restart, close any existing Fan Finder terminal windows first."
    echo
    read -p "Press Enter to exit..."
    exit 1
fi

echo "Starting Fan Finder server..."
echo

# Set environment variables
export FLASK_APP=app/backend/app.py
export FLASK_ENV=production
export PYTHONPATH="$(pwd)"
export FIREBASE_KEY_PATH="$(pwd)/app/config/firebase-key-13504509.json"

echo "Starting Flask server..."
echo "Press Ctrl+C to stop the server"
echo

# Open Chrome maximized and force it to the foreground
(sleep 3 && if [ -d "/Applications/Google Chrome.app" ]; then open -a "Google Chrome" --args --start-maximized "http://localhost:5000" && sleep 3 && osascript -e 'tell application "Google Chrome" to activate' && osascript -e 'tell application "System Events" to set frontmost of process "Google Chrome" to true' && osascript -e 'tell application "System Events" to tell process "Google Chrome" to set value of attribute "AXMaximized" of window 1 to true'; elif [ -d "/Applications/Chrome.app" ]; then open -a "Chrome" --args --start-maximized "http://localhost:5000" && sleep 3 && osascript -e 'tell application "Chrome" to activate' && osascript -e 'tell application "System Events" to set frontmost of process "Chrome" to true' && osascript -e 'tell application "System Events" to tell process "Chrome" to set value of attribute "AXMaximized" of window 1 to true'; else open "http://localhost:5000"; fi) &

# Setup cleanup function
cleanup() {
    echo
    echo "Cleaning up processes..."
    
    # Kill any remaining Python processes related to Fan Finder
    pkill -f "app/backend/app.py" 2>/dev/null
    pkill -f "fan.finder" 2>/dev/null
    
    # Clean up any Chrome processes if they were opened by this script
    # (Only clean up processes we started, not user's regular Chrome)
    
    echo "Cleanup completed."
    exit 0
}

# Register cleanup function for script termination
trap cleanup EXIT INT TERM

# Start Flask server
$PYTHON_CMD app/backend/app.py

# If we reach here, the server stopped
echo
echo "Fan Finder server stopped."
echo

# Cleanup will be called automatically by trap
read -p "Press Enter to exit..."

