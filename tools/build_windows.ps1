# binary-pixel-art Windows onedir + windowed 构建脚本
#
# 职责（刻意保持极薄）：在**已经准备好的** Windows build 环境中执行正式 PyInstaller 构建。
# 本脚本不联网、不安装依赖、不升级 pip、不打包 zip、不上传、不改 Git。
#
# 前置条件（需由使用者自行准备）：
#   - Windows 11 x64（当前目标平台）
#   - Python 3.13（已真人验证 3.13.16）
#   - 已安装 requirements-dev.txt（含 pyinstaller==6.22.3）
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File tools\build_windows.ps1

$ErrorActionPreference = "Stop"

# 1. 确认运行在 Windows
if ($env:OS -ne "Windows_NT") {
    Write-Error "本脚本仅用于 Windows 构建（当前非 Windows 环境）。"
    exit 1
}

# 2. 确认当前 Python 可运行
try {
    $pyVersion = & python --version 2>&1
    Write-Host "Python: $pyVersion"
} catch {
    Write-Error "无法运行 `python`，请确认 Python 3.13 已安装并激活。"
    exit 1
}

# 3. 确认 PyInstaller 可用（使用当前激活环境的模块，而非裸 pyinstaller）
& python -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "当前环境未安装 PyInstaller，请先安装 requirements-dev.txt。"
    exit 1
}

# 4. 从脚本自身位置定位仓库根目录（tools/ 的上一级）
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$SpecFile = Join-Path $RepoRoot "binary-pixel-art.spec"
if (-not (Test-Path $SpecFile)) {
    Write-Error "未找到 spec 文件：$SpecFile"
    exit 1
}
Write-Host "Repo root : $RepoRoot"
Write-Host "Spec file : $SpecFile"

# 5. 调用正式 spec（--clean --noconfirm）；build/ 与 dist/ 位于仓库根
Push-Location $RepoRoot
try {
    & python -m PyInstaller --clean --noconfirm $SpecFile
    if ($LASTEXITCODE -ne 0) {
        Write-Error "PyInstaller 构建失败（exit $LASTEXITCODE）。"
        exit $LASTEXITCODE
    }
} finally {
    Pop-Location
}

# 6. 打印产物位置
$DistDir = Join-Path $RepoRoot "dist\binary-pixel-art"
Write-Host ""
Write-Host "构建完成。产物目录：$DistDir"
Write-Host "可执行文件：$(Join-Path $DistDir 'binary-pixel-art.exe')"
