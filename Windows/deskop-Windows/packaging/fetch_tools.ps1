# Descarga las herramientas que van dentro de la app: yt-dlp, ffmpeg y deno (lo necesita yt-dlp para YouTube).
# Uso (PowerShell, desde deskop-Windows):   ./packaging/fetch_tools.ps1
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$root = Split-Path -Parent $PSScriptRoot
$tools = Join-Path $root "tools"
New-Item -ItemType Directory -Force $tools | Out-Null
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("gp_tools_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force $tmp | Out-Null

function Get-Zip($url, $exeName, $dest) {
    $zip = Join-Path $tmp ($exeName + ".zip")
    $dir = Join-Path $tmp ($exeName + "_x")
    Invoke-WebRequest $url -OutFile $zip
    Expand-Archive $zip $dir -Force
    $found = Get-ChildItem $dir -Recurse -Filter $exeName | Select-Object -First 1
    if (-not $found) { throw "No se encontró $exeName dentro de $url" }
    Copy-Item $found.FullName $dest -Force
}

Write-Host "yt-dlp..."
Invoke-WebRequest "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" -OutFile (Join-Path $tools "yt-dlp.exe")
Write-Host "ffmpeg (build LGPL)..."
Get-Zip "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-lgpl.zip" "ffmpeg.exe" (Join-Path $tools "ffmpeg.exe")
Write-Host "deno..."
Get-Zip "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip" "deno.exe" (Join-Path $tools "deno.exe")

foreach ($n in "yt-dlp.exe", "ffmpeg.exe", "deno.exe") {
    if (-not (Test-Path (Join-Path $tools $n))) { throw "Falta $n" }
}
Write-Host ("yt-dlp " + (& (Join-Path $tools "yt-dlp.exe") --version))
Write-Host ((& (Join-Path $tools "ffmpeg.exe") -version) | Select-Object -First 1)
Write-Host ((& (Join-Path $tools "deno.exe") --version) | Select-Object -First 1)
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
Write-Host "Herramientas listas en $tools"
