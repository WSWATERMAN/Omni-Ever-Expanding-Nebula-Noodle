#!/bin/sh

# Exit immediately if a command exits with a non-zero status
set -e

REPO_URL="https://github.com/WSWATERMAN/Omni-Ever-Expanding-Nebula-Noodle.git"
TARGET_DIR="Omni-Ever-Expanding-Nebula-Noodle"

# Explicitly ensure standard system binary directories are included in the runtime PATH
PATH="$PATH:/usr/bin:/bin:/usr/local/bin"
export PATH

echo "===================================================="
echo " 🌌 Welcome to the Universal AI Shell Installer 🌌 "
echo "===================================================="
echo ""

# ==========================================
# 🛠️ STEP 1: CORE SYSTEM DEPENDENCY CHECK
# ==========================================
echo "🔍 Verifying core system dependencies..."

GIT_CMD=""
# Advanced Git Validation Check (POSIX sh Compliant)
if command -v git >/dev/null 2>&1; then
    echo "✅ Git command path verified via command -v."
    GIT_CMD="git"
elif [ -x "/usr/bin/git" ]; then
    echo "✅ Found Git explicitly at /usr/bin/git"
    GIT_CMD="/usr/bin/git"
elif [ -x "/usr/local/bin/git" ]; then
    echo "✅ Found Git explicitly at /usr/local/bin/git"
    GIT_CMD="/usr/local/bin/git"
else
    echo "❌ Error: 'git' is required but not found in PATH or standard binaries."
    echo "   Please install git or fix your system PATH variable and try again."
    exit 1
fi

# Check for Python3
if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ Error: 'python3' is required to run Akasha. Please install Python 3 and try again."
    exit 1
fi

# Check for Python3 venv module capability
if ! python3 -m venv --help >/dev/null 2>&1; then
    echo "❌ Error: The 'python3-venv' package is missing on your system."
    echo "   To fix this, please install it using your system package manager first."
    echo "   Example: sudo apt install python3-full (or python3-venv)"
    exit 1
fi

# Check for SQLite3 (used by Akasha's internal DB caching layer)
if ! command -v sqlite3 >/dev/null 2>&1; then
    echo "ℹ️  Notice: 'sqlite3' CLI tool not found. Python's built-in sqlite3 library"
    echo "   will still function, but installing the system package is recommended for debugging."
fi

echo "✅ Core binaries and virtual environment modules verified successfully."
echo ""

# ==========================================
# 🔍 STEP 2: VERSION SELECTION VIA GIT TAGS
# ==========================================
echo "🔍 Fetching available versions from GitHub..."
# Fetch remote tags without cloning the entire repo first
AVAILABLE_TAGS=$($GIT_CMD ls-remote --tags --refs "$REPO_URL" | awk -F/ '{print $3}')

if [ -z "$AVAILABLE_TAGS" ]; then
    echo "⚠️  No version tags found on remote. Defaulting to 'main' branch installation."
    SELECTED_VERSION="main"
else
    echo "----------------------------------------------------"
    echo "Available Versions / Code Names found:"
    echo "$AVAILABLE_TAGS" | sed 's/^/  - /'
    echo "----------------------------------------------------"
    echo ""
    echo "👉 Enter the version/codename you want to install"
    echo "   (Or press ENTER to pull the latest 'main' branch code):"
    
    # POSIX compliant read configuration
    read USER_CHOICE

    if [ -z "$USER_CHOICE" ]; then
        SELECTED_VERSION="main"
    else
        # Trim whitespace safely using standard POSIX methods
        SELECTED_VERSION=$(echo "$USER_CHOICE" | awk '{print $1}')
    fi
fi

echo ""
echo "🚀 Preparing workspace to install target version: [$SELECTED_VERSION]..."
echo ""

# Clean up any lingering incomplete installation directories
if [ -d "$TARGET_DIR" ]; then
    echo "🗑️  Found existing folder '$TARGET_DIR'. Removing it to ensure a clean install..."
    rm -rf "$TARGET_DIR"
fi

# ==========================================
# 📥 STEP 3: CLONE AND TARGET ISOLATION
# ==========================================
echo "📥 Cloning repository..."
$GIT_CMD clone "$REPO_URL" "$TARGET_DIR"

cd "$TARGET_DIR"

# Checkout the version chosen by the user
echo "🎯 Checking out version '$SELECTED_VERSION'..."
if [ "$SELECTED_VERSION" != "main" ]; then
    # Verify if the chosen tag actually exists locally after cloning
    if $GIT_CMD rev-parse "$SELECTED_VERSION" >/dev/null 2>&1; then
        $GIT_CMD checkout "$SELECTED_VERSION"
    else
        echo "❌ Error: Version/Tag '$SELECTED_VERSION' not found."
        echo "Please rerun the installer and choose an exact tag from the list."
        exit 1
    fi
fi

# ==========================================
# 📦 STEP 4: ISOLATED VIRTUAL ENV & DEPLOYMENT
# ==========================================
echo ""
echo "📦 Creating isolated Python Virtual Environment (.venv)..."
python3 -m venv .venv

# Map the active binary paths inside the freshly created environment context
VENV_PIP="./.venv/bin/pip"

echo "🔄 Upgrading baseline Python packaging tools inside virtual environment..."
$VENV_PIP install --upgrade pip setuptools wheel

if [ -f "requirements.txt" ]; then
    echo "🐍 Installing dependencies discovered in requirements.txt..."
    $VENV_PIP install -r requirements.txt
    
    # Safety Check: Explicitly guarantee extension packages and Google SDK are integrated
    echo "📊 Injecting core structural monitoring and Google GenAI SDK modules..."
    $VENV_PIP install psutil paramiko google-genai
else
    echo "📝 No requirements.txt found in this version snapshot."
    echo "📦 Injecting default core Python packages directly (openai, prompt_toolkit, psutil, paramiko, google-genai)..."
    $VENV_PIP install openai prompt_toolkit psutil paramiko google-genai
fi

echo ""
echo "===================================================="
echo " 🎉 Installation Successful!"
echo " Version [$SELECTED_VERSION] is locked down in ./$TARGET_DIR"
echo "===================================================="
echo "To dive into your Nebula Noodle space, execute:"
echo "  cd $TARGET_DIR"
echo "  source .venv/bin/activate"
echo "  python3 akasha.py"
echo "===================================================="
