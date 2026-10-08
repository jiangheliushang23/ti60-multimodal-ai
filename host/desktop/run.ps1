param([switch]$Demo)
$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw '请先按 host/desktop/README.md 创建 .venv 并安装 requirements.txt。'
}
$appPath = Join-Path $PSScriptRoot 'app.py'
if ($Demo) { & $pythonPath -B $appPath --demo }
else { & $pythonPath -B $appPath }
