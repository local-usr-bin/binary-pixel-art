# binary-pixel-art Windows onedir + windowed build script
#
# Purpose (intentionally thin): run the formal PyInstaller build in an
# ALREADY-PREPARED Windows build environment. This script does NOT go online,
# does NOT install dependencies, does NOT upgrade pip, does NOT create a zip,
# does NOT upload anything, and does NOT touch Git.
#
# Prerequisites (prepared by the user):
#   - Windows 11 x64 (current target platform)
#   - Python 3.13 (validated on 3.13.16)
#   - requirements-dev.txt installed (includes pyinstaller==6.22.3)
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools\build_windows.ps1

$ErrorActionPreference = "Stop"

# 1. Confirm we are running on Windows
if ($env:OS -ne "Windows_NT") {
    Write-Error "This script is for Windows builds only (current environment is not Windows)."
    exit 1
}

# 2. Confirm the current Python runs
try {
    $pyVersion = & python --version 2>&1
    Write-Host "Python: $pyVersion"
} catch {
    Write-Error "Cannot run 'python'. Please ensure Python 3.13 is installed and activated."
    exit 1
}

# 3. Confirm PyInstaller is available (use the current env module, not bare 'pyinstaller')
& python -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller is not installed in the current environment. Please install requirements-dev.txt first."
    exit 1
}

# 4. Locate the repository root from this script's own location (parent of tools/)
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$SpecFile = Join-Path $RepoRoot "binary-pixel-art.spec"
if (-not (Test-Path $SpecFile)) {
    Write-Error "Spec file not found: $SpecFile"
    exit 1
}
Write-Host "Repo root : $RepoRoot"
Write-Host "Spec file : $SpecFile"

# 5. Invoke the formal spec (--clean --noconfirm); build/ and dist/ land in the repo root
Push-Location $RepoRoot
try {
    & python -m PyInstaller --clean --noconfirm $SpecFile
    if ($LASTEXITCODE -ne 0) {
        Write-Error "PyInstaller build failed (exit $LASTEXITCODE)."
        exit $LASTEXITCODE
    }
} finally {
    Pop-Location
}

# 6. Print the artifact location
$DistDir = Join-Path $RepoRoot "dist\binary-pixel-art"
Write-Host ""
Write-Host "Build complete. Artifact directory: $DistDir"
Write-Host "Executable: $(Join-Path $DistDir 'binary-pixel-art.exe')"
