<#
.SYNOPSIS
    Sends this PC's stats to the InkyPi PC Stats plugin.

.DESCRIPTION
    Every IntervalSeconds, collects CPU, GPU, RAM, disk, IP and focused-window info,
    writes it as "key: value" lines, and copies the file to the Pi with scp.
    Replaces pc_sync_hidden.bat, which relied on wmic (removed from recent Windows 11 builds).

    scp runs in batch mode, so set up key-based SSH to the Pi first:
        ssh-keygen -t ed25519
        type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh walju@walju.local "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"

.EXAMPLE
    .\pc_sync.ps1 -DryRun
    Collects stats once and prints them without uploading.

.EXAMPLE
    .\pc_sync.ps1 -Once
    Collects and uploads once, reporting any scp error.
#>
param(
    [string]$DestUser = "walju",
    [string]$DestHost = "walju.local",
    [string]$DestPath = "/home/walju/pc_stats.txt",  # must match pc_file in pc_stats.py
    [int]$IntervalSeconds = 60,
    [string]$Drive = "C",
    [switch]$Once,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

Add-Type -Namespace PcSync -Name Win32 -MemberDefinition @"
[DllImport("user32.dll")] public static extern System.IntPtr GetForegroundWindow();
[DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(System.IntPtr hWnd, System.Text.StringBuilder text, int count);
"@

$script:extIp = $null
$script:extIpFetched = [datetime]::MinValue

function Get-CpuLoad {
    $load = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
    return [math]::Round($load)
}

function Get-GpuLoad {
    # NVIDIA cards report through nvidia-smi; otherwise fall back to the 3D engine perf counter.
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        $out = & nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>$null | Select-Object -First 1
        if ($out -match '^\s*(\d+)') { return [int]$Matches[1] }
    }
    try {
        $samples = (Get-Counter '\GPU Engine(*engtype_3D)\Utilization Percentage' -ErrorAction Stop).CounterSamples
        return [math]::Min(100, [math]::Round(($samples | Measure-Object -Property CookedValue -Sum).Sum))
    } catch {
        return $null
    }
}

function Get-RamUsage {
    $os = Get-CimInstance Win32_OperatingSystem
    return [math]::Round(100 * (1 - $os.FreePhysicalMemory / $os.TotalVisibleMemorySize))
}

function Get-DiskFree {
    $free = (Get-PSDrive -Name $Drive -PSProvider FileSystem).Free
    return [math]::Round($free / 1GB, 1)
}

function Get-LocalIp {
    $config = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq "Up" } | Select-Object -First 1
    if ($config) { return $config.IPv4Address.IPAddress | Select-Object -First 1 }
    return $null
}

function Get-ExternalIp {
    # Cache for 15 minutes so the loop doesn't hit ipify every interval.
    if ((Get-Date) - $script:extIpFetched -gt [timespan]::FromMinutes(15)) {
        try {
            $script:extIp = (Invoke-RestMethod -Uri "https://api.ipify.org" -TimeoutSec 5).Trim()
        } catch {
            $script:extIp = $null
        }
        $script:extIpFetched = Get-Date
    }
    return $script:extIp
}

function Get-FocusedWindow {
    $text = New-Object System.Text.StringBuilder 256
    [void][PcSync.Win32]::GetWindowText([PcSync.Win32]::GetForegroundWindow(), $text, $text.Capacity)
    $title = $text.ToString().Trim()
    if ($title.Length -gt 20) { $title = $title.Substring(0, 20) }
    return $title
}

function Get-StatsText {
    $stats = [ordered]@{
        cpu     = "$(Get-CpuLoad)%"
        gpu     = $null
        ram     = "$(Get-RamUsage)%"
        ssd     = "$(Get-DiskFree)GB Free"
        localip = Get-LocalIp
        extip   = Get-ExternalIp
        focus   = Get-FocusedWindow
    }
    $gpu = Get-GpuLoad
    if ($null -ne $gpu) { $stats.gpu = "$gpu%" }

    # The plugin skips keys that are missing, so leave out anything we couldn't read.
    $lines = foreach ($key in $stats.Keys) {
        if ($stats[$key]) { "${key}: $($stats[$key])" }
    }
    return ($lines -join "`n") + "`n"
}

$tempFile = Join-Path $env:TEMP "pc_stats.txt"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false

while ($true) {
    $content = Get-StatsText

    if ($DryRun) {
        Write-Output $content
        break
    }

    [System.IO.File]::WriteAllText($tempFile, $content, $utf8NoBom)
    $scpOutput = & scp -q -o ConnectTimeout=5 -o BatchMode=yes $tempFile "${DestUser}@${DestHost}:${DestPath}" 2>&1
    if ($LASTEXITCODE -ne 0 -and $Once) {
        Write-Error "scp to ${DestUser}@${DestHost} failed: $scpOutput"
    }
    Remove-Item $tempFile -ErrorAction SilentlyContinue

    if ($Once) { break }
    Start-Sleep -Seconds $IntervalSeconds
}
