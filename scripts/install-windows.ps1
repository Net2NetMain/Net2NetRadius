#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$Distribution = "Ubuntu-24.04"
)

$ErrorActionPreference = "Stop"

Write-Host "Net2Net Local RADIUS Manager - Windows development installer" -ForegroundColor Cyan

$wslFeature = Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux
$vmFeature = Get-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform

if ($wslFeature.State -ne "Enabled" -or $vmFeature.State -ne "Enabled") {
    Write-Host "Enabling WSL2 features. Windows must restart before installation continues." -ForegroundColor Yellow
    Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux -All -NoRestart | Out-Null
    Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform -All -NoRestart | Out-Null
    Write-Host "Restart Windows, then run this same script again." -ForegroundColor Yellow
    exit 3010
}

wsl --set-default-version 2
$installed = (wsl --list --quiet) -replace "`0", "" | Where-Object { $_.Trim() -eq $Distribution }
if (-not $installed) {
    Write-Host "Installing $Distribution. Complete the Linux username prompt if Windows opens one." -ForegroundColor Cyan
    wsl --install --distribution $Distribution --no-launch
}

$scriptPath = Join-Path $PSScriptRoot "bootstrap-wsl.sh"
$linuxScript = (wsl -d $Distribution wslpath -a ($scriptPath -replace '\\','/')).Trim()
wsl -d $Distribution bash $linuxScript
if ($LASTEXITCODE -ne 0) {
    throw "WSL bootstrap failed with exit code $LASTEXITCODE. Review the Linux output above."
}

Write-Host "WSL services installed. Next: copy .env.example to .env and set local secrets." -ForegroundColor Green
