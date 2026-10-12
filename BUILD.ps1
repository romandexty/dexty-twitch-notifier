$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (!(Test-Path -LiteralPath '.build-env/Scripts/python.exe')) {
    & py -3.12 -m venv .build-env
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 (64-bit) first.' }
}
$buildPython = Join-Path $PSScriptRoot '.build-env/Scripts/python.exe'
& $buildPython -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $buildPython -m PyInstaller --noconfirm DextyTwitchNotifier.spec
if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
Copy-Item -LiteralPath ThirdPartyNotices -Destination dist/DextyTwitchNotifier -Recurse -Force
$compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1
if (!$compiler) {
    $compiler = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6/ISCC.exe'
}
if (!(Test-Path -LiteralPath $compiler)) { throw 'Install Inno Setup 6 or add ISCC.exe to PATH.' }
& $compiler setup.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
Write-Host 'Ready: output/Dexty_Twitch_Notifier_Setup_v1.0.0.exe'




