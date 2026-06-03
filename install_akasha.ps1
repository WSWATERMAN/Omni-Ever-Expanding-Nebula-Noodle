 # install_akasha.ps1
# Windows PowerShell Installer for akaSHa - Universal AI Shell

$ErrorActionPreference = "Stop"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "          akaSHa - Universal AI Shell Windows Installer" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# 1. Define Standard Paths
$InstallDir = Join-Path $HOME "akasha"
$VenvDir = Join-Path $InstallDir "venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"

# 2. Ensure Target Directory Exists
if (-not (Test-Path $InstallDir)) {
    Write-Host "[+] Creating application directory at $InstallDir..." -ForegroundColor Green
    New-Item -ItemType Directory -Path $InstallDir | Out-Null
} else {
    Write-Host "[*] Application directory $InstallDir already exists." -ForegroundColor Yellow
}

# 3. Verify Python Installation
try {
    $PythonCheck = python --version 2>&1
    Write-Host "[+] Found system $PythonCheck" -ForegroundColor Green
} catch {
    Write-Error "Python 3 is required but could not be found in your PATH. Please install Python and try again."
    Exit
}

# 4. Initialize and Upgrade Virtual Environment
if (-not (Test-Path $VenvDir)) {
    Write-Host "[+] Provisioning isolated Python virtual environment..." -ForegroundColor Green
    python -m venv $VenvDir
}

Write-Host "[+] Upgrading pip and core dependencies inside venv..." -ForegroundColor Green
& $VenvPython -m pip install --upgrade pip | Out-Null

# 5. Install Required Application Dependencies
Write-Host "[+] Installing telemetry, networking, and prompt toolkits..." -ForegroundColor Green
# Note: prompt-toolkit, google-genai, paramiko, netmiko, and psutil are needed for full features
& $VenvPip install --upgrade prompt-toolkit google-genai paramiko netmiko psutil

# 6. Configure Gemini API Key Securely
$CurrentKey = [Environment]::GetEnvironmentVariable("GEMINI_API_KEY", "User")
if (-not $CurrentKey) {
    Write-Host "`n[!] GEMINI_API_KEY environment variable not found." -ForegroundColor Yellow
    $InputKey = Read-Host "Please enter your Gemini API Key (or press Enter to skip and set later)"
    if ($InputKey) {
        [Environment]::SetEnvironmentVariable("GEMINI_API_KEY", $InputKey.Trim(), "User")
        $env:GEMINI_API_KEY = $InputKey.Trim()
        Write-Host "[+] Gemini API Key saved securely to User Environment Variables." -ForegroundColor Green
    }
} else {
    Write-Host "[*] Active GEMINI_API_KEY detected in environment context." -ForegroundColor Green
}

# 7. Create PowerShell Global Invocation Shortcut (Alias/Function)
Write-Host "`n[+] Registering global 'akasha' terminal shortcut..." -ForegroundColor Green

$ProfileDir = Split-Path $PROFILE -Parent
if (-not (Test-Path $ProfileDir)) {
    New-Item -ItemType Directory -Path $ProfileDir | Out-Null
}
if (-not (Test-Path $PROFILE)) {
    New-Item -ItemType File -Path $PROFILE | Out-Null
}

# Payload block to append to the profile
$ShortcutFunction = @"

# akaSHa AI Shell Global Entrypoint Launcher
function akasha {
    Set-Location "$InstallDir"
    & "$VenvPython" akasha.py
}
"@

# Check if the shortcut is already installed to avoid duplicate clutter
$ProfileContent = Get-Content $PROFILE -Raw
if ($ProfileContent -notlike "*function akasha*") {
    Add-Content -Path $PROFILE -Value $ShortcutFunction
    Write-Host "[+] Successfully mapped 'akasha' entrypoint into your PowerShell Profile." -ForegroundColor Green
} else {
    Write-Host "[*] Global 'akasha' shortcut function already defined in your profile." -ForegroundColor Yellow
}

Write-Host "`n==================================================================" -ForegroundColor Cyan
Write-Host "🚀 Installation Complete!" -ForegroundColor Green
Write-Host "1. Ensure your 'akasha.py' script file is placed inside: $InstallDir" -ForegroundColor White
Write-Host "2. Restart your PowerShell window or run: . `$PROFILE" -ForegroundColor White
Write-Host "3. Launch the environment anywhere by running: akasha" -ForegroundColor Highlighting
Write-Host "==================================================================" -ForegroundColor Cyan 
