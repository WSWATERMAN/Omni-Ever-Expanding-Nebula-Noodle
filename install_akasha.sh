#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -e

REPO_URL="https://github.com/WSWATERMAN/Omni-Ever-Expanding-Nebula-Noodle.git"
TARGET_DIR="Omni-Ever-Expanding-Nebula-Noodle"

echo "===================================================="
echo " 🌌 Welcome to the Universal AI Shell Installer 🌌 "
echo "===================================================="
echo ""

# Check for git dependency
if ! command -v git &> /dev/null; then
    echo "❌ Error: 'git' is required but not installed. Please install git and try again."
    exit 1
fi

echo "🔍 Fetching available versions from GitHub..."
# Fetch remote tags without cloning the entire repo first
AVAILABLE_TAGS=$(git ls-remote --tags --refs $REPO_URL | awk -F/ '{print $3}')

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
    read -r USER_CHOICE

    if [ -z "$USER_CHOICE" ]; then
        SELECTED_VERSION="main"
    else
        # Trim any accidental whitespace
        SELECTED_VERSION=$(echo "$USER_CHOICE" | xargs)
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

# Clone the repository
echo "📥 Cloning repository..."
git clone $REPO_URL $TARGET_DIR

cd "$TARGET_DIR"

# Checkout the version chosen by the user
echo "🎯 Checking out version '$SELECTED_VERSION'..."
if [ "$SELECTED_VERSION" != "main" ]; then
    # Verify if the chosen tag actually exists locally after cloning
    if git rev-parse "$SELECTED_VERSION" >/dev/null 2>&1; then
        git checkout "$SELECTED_VERSION"
    else
        echo "❌ Error: Version/Tag '$SELECTED_VERSION' not found."
        echo "Please rerun the installer and choose an exact tag from the list."
        exit 1
    fi
fi

# --- ENVIRONMENT SETUP ---
echo ""
echo "📦 Setting up local environment and dependencies..."

if command -v pip3 &> /dev/null; then
    # Install dependencies if you have a requirements.txt file
    if [ -f "requirements.txt" ]; then
        echo "🐍 Installing Python dependencies..."
        pip3 install -r requirements.txt
    fi
else
    echo "⚠️  Warning: 'pip3' not found. Skipping automated dependency installation."
fi

echo ""
echo "===================================================="
echo " 🎉 Installation Successful!"
echo " Version [$SELECTED_VERSION] is locked down in ./$TARGET_DIR"
echo "===================================================="
echo "To dive into your Nebula Noodle space, execute:"
echo "  cd $TARGET_DIR && python3 akasha.py"
echo "===================================================="
