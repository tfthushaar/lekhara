# Builds dist\lekhara-connector.exe, a single Windows program, with PyInstaller.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python -m pip install --upgrade pyinstaller
python -m PyInstaller --onefile --console --name lekhara-connector lekhara_connector.py
Write-Output "Built dist\lekhara-connector.exe. Sign it before handing it out."
