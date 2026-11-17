param(
    [string]$OutputDir = "build/windows",
    [int]$Jobs = 4
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path

Push-Location $ProjectRoot
try {
    $Version = (Get-Content -Raw "VERSION").Trim()
    New-Item -ItemType Directory -Force $OutputDir | Out-Null
    python -m nuitka `
      --standalone `
      --msvc=latest `
      --assume-yes-for-downloads `
      --windows-console-mode=disable `
      --windows-icon-from-ico=assets/icons/app_icon.ico `
      --windows-product-name="Blink Call" `
      --windows-file-description="Blink Call" `
      --windows-product-version=$Version `
      --windows-file-version=$Version `
      --enable-plugin=pyside6 `
      --include-package=blink_call `
      --include-package=tzdata `
      --include-package-data=tzdata `
      --include-data-file=VERSION=VERSION `
      --include-data-file=LICENSE=LICENSE `
      --include-data-dir=assets=assets `
      --jobs=$Jobs `
      --output-dir=$OutputDir `
      --report="$OutputDir/nuitka-report.xml" `
      --output-filename=BlinkCall.exe `
      blink_call/setup_app.py
    if ($LASTEXITCODE -ne 0) {
        throw "Nuitka build failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}
