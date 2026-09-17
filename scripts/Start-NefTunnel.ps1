[CmdletBinding()]
param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $root '.runtime'
$exe = Join-Path $runtime 'cloudflared.exe'
$expectedHash = '547057326266f0e1c7d50d102dbd22ff283d740c055bd61e94f10e2c606f89af'

if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw 'Missing .runtime/cloudflared.exe. Follow docs/demo-playbook.md.'
}
if ((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) {
    throw 'cloudflared does not match the verified 2026.9.0 Windows amd64 release.'
}

$response = Invoke-WebRequest -Uri 'http://127.0.0.1:8069/api/v1/services' -UseBasicParsing -TimeoutSec 10
if ($response.StatusCode -ne 200) { throw 'Local NEF service is not ready.' }
$null = $response.Content | ConvertFrom-Json
Write-Output 'Verified cloudflared binary; local NEF services endpoint returned HTTP 200.'
if ($CheckOnly) { return }

$service = Get-Service -Name Cloudflared -ErrorAction SilentlyContinue
if ($null -ne $service -and $service.Status -eq 'Running') {
    throw 'The Windows Cloudflared service is already running. Reuse it instead of starting another connector.'
}
$running = @(Get-Process -Name cloudflared -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -eq $exe })
if ($running.Count -gt 0) {
    throw 'This project already has a cloudflared process. Check it before starting another.'
}

# The token is never placed in command arguments, source files, or shell history.
$previousToken = [Environment]::GetEnvironmentVariable('TUNNEL_TOKEN', 'Process')
$secret = $null
$credential = $null
try {
    if ([string]::IsNullOrWhiteSpace($previousToken)) {
        $secret = Read-Host 'Paste the token for nef-demo-windows (input hidden)' -AsSecureString
        $credential = [System.Net.NetworkCredential]::new('', $secret)
        if ([string]::IsNullOrWhiteSpace($credential.Password)) { throw 'Tunnel token is empty.' }
        [Environment]::SetEnvironmentVariable('TUNNEL_TOKEN', $credential.Password, 'Process')
    }
    Write-Output 'Starting Tunnel in this terminal. Keep it open; Ctrl+C stops this connector.'
    & $exe tunnel --no-autoupdate --metrics '127.0.0.1:20769' --loglevel info --logfile (Join-Path $runtime 'cloudflared.log') run
    if ($LASTEXITCODE -ne 0) { throw "cloudflared exited with code $LASTEXITCODE." }
}
finally {
    [Environment]::SetEnvironmentVariable('TUNNEL_TOKEN', $previousToken, 'Process')
    $credential = $null
    if ($null -ne $secret) { $secret.Dispose() }
}
