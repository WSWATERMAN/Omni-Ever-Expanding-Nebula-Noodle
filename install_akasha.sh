#!/bin/sh
# ==============================================================================
# 🌌 Universal AI Shell Installer: Akasha & Dalikmata Core Initialization
# ==============================================================================
set -e

# Force inject standard system binary paths to ensure tool resolution
export PATH="/usr/bin:/bin:/usr/local/bin:/usr/sbin:/sbin:$PATH"

echo "===================================================================="
echo "🌌 Welcome to the Universal AI Shell Installer 🌌"
echo "        Initializing Systems: Akasha & Dalikmata Framework"
echo "===================================================================="

# ------------------------------------------------------------------------------
# STEP 1: CORE SYSTEM DEPENDENCY CHECK
# ------------------------------------------------------------------------------
echo "🔍 Verifying core system dependencies..."

GIT_CMD=""
if [ -x "/usr/bin/git" ]; then
    GIT_CMD="/usr/bin/git"
elif command -v git >/dev/null 2>&1; then
    GIT_CMD="git"
fi

if [ -z "$GIT_CMD" ]; then
    echo "❌ Error: 'git' is required but not installed." >&2
    echo "Please install git via your system package manager and try again." >&2
    exit 1
fi

PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        PYTHON_CMD="$cmd"
        break
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "❌ Error: Python 3 is required but not found." >&2
    exit 1
fi

echo "✅ Core dependencies verified (Git & Python discovered)."

# ------------------------------------------------------------------------------
# STEP 2: DYNAMIC VERSION TARGETING VIA GIT TAGS
# ------------------------------------------------------------------------------
REPO_URL="https://github.com/WSWATERMAN/Omni-Ever-Expanding-Nebula-Noodle.git"
TARGET_DIR="Omni-Ever-Expanding-Nebula-Noodle"

echo "\n📡 Fetching available workspace releases from GitHub..."

# Inspect remote tags dynamically before pulling massive files
TAGS=$($GIT_CMD ls-remote --tags $REPO_URL | awk '{print $2}' | sed 's|refs/tags/||' | grep -v '\^{}')

if [ -z "$TAGS" ]; then
    echo "⚠️  No historical distribution tags found. Defaulting to 'main' production line."
    SELECTED_VERSION="main"
else
    echo "--------------------------------------------------------------------"
    echo "Available Environments & Code Names:"
    echo "--------------------------------------------------------------------"
    echo "$TAGS"
    echo "--------------------------------------------------------------------"
    echo "👉 Enter specific version tag (e.g., v1.0.0-Akasha) or press [ENTER]"
    echo "   to automatically track the latest cutting-edge main production branch:"
    printf "Selection: "
    read -r USER_INPUT
    
    if [ -z "$USER_INPUT" ]; then
        SELECTED_VERSION="main"
    else
        SELECTED_VERSION="$USER_INPUT"
    fi
fi

# ------------------------------------------------------------------------------
# STEP 3: REPOSITORY ORCHESTRATION & SNAPSHOT CHECKOUT
# ------------------------------------------------------------------------------
if [ -d "$TARGET_DIR" ]; then
    echo "\n📦 Local repository directory exists. Stashing alterations and syncing..."
    cd "$TARGET_DIR"
    $GIT_CMD fetch --all --tags
else
    echo "\n🏎️ Cloning project architecture into: $TARGET_DIR..."
    $GIT_CMD clone $REPO_URL
    cd "$TARGET_DIR"
fi

echo "🔄 Shifting workspace state to target tracking node: [$SELECTED_VERSION]..."
$GIT_CMD checkout "$SELECTED_VERSION"

# ------------------------------------------------------------------------------
# STEP 4: ISOLATED PYTHON VENV PROVISIONING (PEP 668 COMPLIANT)
# ------------------------------------------------------------------------------
echo "\n🛠️ Establishing an isolated Python Virtual Environment (.venv)..."
# Ensure python3-venv / python3-full utilities are utilized cleanly
$PYTHON_CMD -m venv .venv

# Target the local virtual environment binaries directly to bypass system restrictions
VENV_PYTHON="./.venv/bin/python"
VENV_PIP="./.venv/bin/pip"

echo "🔄 Upgrading baseline virtual environment packaging tools..."
$VENV_PYTHON -m pip install --upgrade pip setuptools wheel

# ------------------------------------------------------------------------------
# STEP 5: DEPENDENCY INJECTION (AKASHA KNOWLEDGE + DALIKMATA TELEMETRY/HEALING)
# ------------------------------------------------------------------------------
echo "\n📦 Loading foundational environment multi-agent dependencies..."

# Core array of explicit dependencies for Akasha (Knowledge) & Dalikmata (Healing/SSH Remote Tuning)
CORE_PACKAGES="google-genai openai prompt_toolkit psutil paramiko"

if [ -f "requirements.txt" ]; then
    echo "📄 Manifest 'requirements.txt' detected. Resolving pinned components..."
    $VENV_PIP install -r requirements.txt
fi

echo "🚀 Injecting verified functional packages ($CORE_PACKAGES)..."
$VENV_PIP install $CORE_PACKAGES

# ------------------------------------------------------------------------------
# STEP 6: VERIFICATION & COMPLETION
# ------------------------------------------------------------------------------
echo "\n===================================================================="
echo "🎉 System Setup Complete! The Ecosystem is Ready."
echo "===================================================================="
echo "  - Knowledge Matrix: Akasha Engine"
echo "  - Restoration Matrix: Dalikmata Core Enabled"
echo "--------------------------------------------------------------------"
echo "To activate your isolated sandbox manually, run:"
echo "    source $TARGET_DIR/.venv/bin/activate"
echo ""
echo "To boot up the universal system console immediately, execute:"
echo "    $TARGET_DIR/.venv/bin/python $TARGET_DIR/akasha.py"
echo "===================================================================="
