#!/bin/bash
# Pro YouTube Downloader - macOS Launcher
# Double-click to run (no Terminal needed)

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_ok() { echo -e "${GREEN}[OK]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[!!]${NC} $1"; }
print_err() { echo -e "${RED}[XX]${NC} $1"; }
print_info() { echo -e "${CYAN}[..]${NC} $1"; }

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

print_info "Pro YouTube Downloader - macOS Launcher"
echo ""

# 1. DETECT CHIP
print_info "Detecting chip..."
CHIP_OUTPUT=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "")
if [[ "$CHIP_OUTPUT" == *"Apple"* ]]; then
    BREW_PATH="/opt/homebrew"
    CHIP_TYPE="apple_silicon"
    print_ok "Apple Silicon detected (M1/M2/M3) → Using $BREW_PATH"
else
    BREW_PATH="/usr/local"
    CHIP_TYPE="intel"
    print_ok "Intel Mac detected → Using $BREW_PATH"
fi

# 2. CHECK HOMEBREW
print_info "Checking Homebrew..."
if ! command -v brew &> /dev/null; then
    print_warn "Homebrew not found. Installing..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    
    # Add to PATH for current session
    if [[ "$CHIP_TYPE" == "apple_silicon" ]]; then
        eval "$($BREW_PATH/bin/brew shellenv)"
    else
        eval "$($BREW_PATH/bin/brew shellenv)"
    fi
    
    # Persist in ~/.zprofile
    if [[ "$CHIP_TYPE" == "apple_silicon" ]]; then
        echo 'eval "/opt/homebrew/bin/brew shellenv"' >> ~/.zprofile 2>/dev/null || true
    else
        echo 'eval "/usr/local/bin/brew shellenv"' >> ~/.zprofile 2>/dev/null || true
    fi
    
    print_ok "Homebrew installed and configured"
else
    print_ok "Homebrew already installed"
fi

# Ensure brew is in PATH
eval "$($BREW_PATH/bin/brew shellenv)" 2>/dev/null || true

RESTART_NEEDED=0

# 3. CHECK PYTHON 3
print_info "Checking Python 3..."
if ! command -v python3 &> /dev/null; then
    print_warn "Python 3 not found. Installing..."
    brew install python
    RESTART_NEEDED=1
    print_ok "Python 3 installed"
else
    print_ok "Python 3 already installed ($(python3 --version))"
fi

# 4. CHECK FFMPEG
print_info "Checking FFmpeg..."
ENCODER_TYPE="unknown"
if ! command -v ffmpeg &> /dev/null; then
    print_warn "FFmpeg not found. Installing..."
    brew install ffmpeg
    print_ok "FFmpeg installed"
else
    print_ok "FFmpeg already installed ($(ffmpeg -version | head -n1))"
fi

# Check for hevc_videotoolbox encoder
print_info "Checking for hardware encoder..."
if ffmpeg -hide_banner -encoders 2>/dev/null | grep -q "hevc_videotoolbox"; then
    ENCODER_TYPE="hardware"
    print_ok "hevc_videotoolbox found → Hardware GPU encoding available"
else
    ENCODER_TYPE="software"
    print_warn "hevc_videotoolbox not found → Will use libx265 CPU fallback"
fi

# 5. HANDLE RESTART WARNING
if [[ $RESTART_NEEDED -eq 1 ]]; then
    echo ""
    print_warn "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    print_warn "  RESTART REQUIRED"
    print_warn "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    print_warn "  New software was installed."
    print_warn "  Please close this window and double-click"
    print_warn "  run_app.command again to continue."
    print_warn "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    exit 0
fi

# 6. PYTHON VIRTUAL ENVIRONMENT
print_info "Setting up virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    print_ok "Virtual environment created at .venv/"
else
    print_ok "Virtual environment already exists"
fi

# Activate virtual environment
source .venv/bin/activate
print_ok "Virtual environment activated"

# 7. INSTALL PYTHON LIBRARIES
print_info "Installing Python packages..."
pip install -q -U yt-dlp streamlit
print_ok "Packages installed/updated (yt-dlp, streamlit)"

# 8. LAUNCH APP
print_info "Starting Streamlit app..."
echo ""
print_ok "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
print_ok "  Launching Pro YouTube Downloader"
print_ok "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
print_info "Opening browser in 3 seconds..."

# Open browser after delay
(sleep 3 && open http://localhost:8501) &

# Run Streamlit
streamlit run app.py
