<#
.SYNOPSIS
    Record your own voice line for the Nyanko-sensei desktop pet.

.DESCRIPTION
    The pet's click reaction plays a clip named `natsume` from its voice pack.
    That clip is the character's line from the anime, which is a commercial
    recording — the plugin cannot ship it, so you supply your own copy.

    This helper records from a microphone, trims the silence around the take,
    normalises the level and writes it into the user voice pack, where the
    plugin picks it up on the next page load. No package files are touched.

    What you record is your responsibility: if you are capturing audio from a
    source you own, keep it for personal use and do not redistribute the
    resulting file.

.PARAMETER Clip
    Target clip name. Defaults to `natsume`.

.PARAMETER Seconds
    Maximum recording length. Recording is manual-stop (press Enter) as well.

.PARAMETER Device
    DirectShow audio input name. Omit to list the available devices.

.PARAMETER Pack
    Voice pack directory name to write into. Defaults to `custom`.

.EXAMPLE
    pwsh -File tools/record-voice.ps1 -Device
    Lists the microphone names ffmpeg can see.

.EXAMPLE
    pwsh -File tools/record-voice.ps1 -Device "Microphone (Realtek(R) Audio)" -Seconds 6
    Records up to six seconds, then trims and normalises it into the pet.
#>
[CmdletBinding()]
param(
    [string]$Clip = 'natsume',
    [int]$Seconds = 8,
    [string]$Device,
    [string]$Pack = 'custom',
    [switch]$ListDevices
)

$ErrorActionPreference = 'Stop'

function Resolve-Ffmpeg {
    $cmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $guess = Get-ChildItem 'D:\ffmpeg-*\bin\ffmpeg.exe' -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($guess) { return $guess.FullName }
    throw 'ffmpeg was not found on PATH and no D:\ffmpeg-*\bin\ffmpeg.exe was found.'
}

$ffmpeg = Resolve-Ffmpeg
Write-Host "ffmpeg: $ffmpeg" -ForegroundColor DarkGray

# --- enumerate devices -----------------------------------------------------
$deviceList = & $ffmpeg -hide_banner -list_devices true -f dshow -i dummy 2>&1 |
    Select-String 'dshow.*"([^"]+)"' |
    ForEach-Object { $_.Matches[0].Groups[1].Value } |
    Where-Object { $_ -match 'audio|麦克风|Microphone|Stereo|Line|Mix' }

if ($ListDevices) {
    if (-not $deviceList) { Write-Host 'No DirectShow audio devices found.' -ForegroundColor Yellow }
    else { $deviceList | ForEach-Object { Write-Host "  $_" } }
    return
}

if (-not $Device) {
    if ($deviceList.Count -eq 1) { $Device = $deviceList[0] }
    else {
        Write-Host 'Several audio inputs were found; pick one with -Device:' -ForegroundColor Yellow
        $deviceList | ForEach-Object { Write-Host "  $_" }
        Write-Host ''
        Write-Host "Example: pwsh -File tools/record-voice.ps1 -Device `"$($deviceList[0])`"" -ForegroundColor DarkGray
        return
    }
}

# --- target -----------------------------------------------------------------
$home_ = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $HOME '.dsh' }
$packDir = Join-Path $home_ "dsh-nyanko-sensei\voice\$Pack"
New-Item -ItemType Directory -Force -Path $packDir | Out-Null
$target = Join-Path $packDir "$Clip.mp3"
$raw = Join-Path ([System.IO.Path]::GetTempPath()) "nyanko-$Clip-raw.wav"

Write-Host ''
Write-Host "Recording clip '$Clip' from '$Device'" -ForegroundColor Cyan
Write-Host 'Get ready — recording starts in 3 seconds. Press Enter to stop early.' -ForegroundColor Cyan
Start-Sleep -Seconds 3

$proc = Start-Process -FilePath $ffmpeg -PassThru -NoNewWindow -ArgumentList @(
    '-hide_banner', '-loglevel', 'error', '-y',
    '-f', 'dshow', '-i', "audio=$Device",
    '-t', "$Seconds", '-ac', '1', '-ar', '44100', $raw
)

# Manual stop: writing to the process's stdin would need a pipe, so watch for a
# keypress on this side and kill the recorder when it arrives.
$deadline = (Get-Date).AddSeconds($Seconds)
while (-not $proc.HasExited -and (Get-Date) -lt $deadline) {
    if ([Console]::KeyAvailable) {
        [Console]::ReadKey($true) | Out-Null
        try { $proc.Kill() } catch { }
        break
    }
    Start-Sleep -Milliseconds 120
}
try { $proc.WaitForExit(3000) | Out-Null } catch { }

if (-not (Test-Path $raw)) { throw 'Recording produced no file — check the device name.' }

# --- trim + normalise -------------------------------------------------------
# `silenceremove` from both ends drops the lead-in and the dead air after the
# take; `loudnorm` brings every take to a comparable level so a quiet recording
# is not lost under the animation. The three stages go in ONE -af chain —
# repeating -af would silently replace the previous filter.
& $ffmpeg -hide_banner -loglevel error -y -i $raw `
    -af "silenceremove=start_periods=1:start_silence=0.05:start_threshold=-45dB:detection=peak,areverse,silenceremove=start_periods=1:start_silence=0.05:start_threshold=-45dB:detection=peak,areverse,loudnorm=I=-18:TP=-1.5:LRA=11" `
    -ac 1 -ar 44100 -b:a 128k $target

Remove-Item $raw -ErrorAction SilentlyContinue

if (Test-Path $target) {
    $size = [math]::Round((Get-Item $target).Length / 1KB)
    Write-Host ''
    Write-Host "Wrote $target ($size KiB)" -ForegroundColor Green
    Write-Host 'Reload the DSH page; the pet will use it on the next click.' -ForegroundColor Green
    Write-Host "Tip: to use a whole folder of takes as a pack, drop the files into $packDir" -ForegroundColor DarkGray
} else {
    throw 'Encoding failed; the raw take was removed.'
}
