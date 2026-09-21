param(
    [string]$PythonPath = "",
    [ValidateSet("127.0.0.1", "0.0.0.0")]
    [string]$ListenAddress = "127.0.0.1",
    [ValidateRange(1024, 65535)]
    [int]$Port = 8069
)

$ErrorActionPreference = "Stop"
$taskName = "NEF-Expo"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$runner = Join-Path $PSScriptRoot "run_nef_background.py"
if (-not $PythonPath) {
    $PythonPath = (Get-Command python.exe -ErrorAction Stop).Source
}
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
$pythonWindowless = Join-Path (Split-Path -Parent $PythonPath) "pythonw.exe"
if (-not (Test-Path -LiteralPath $pythonWindowless)) {
    throw "pythonw.exe is missing beside Python. Use a standard Windows Python installation."
}
$arguments = '-u "{0}" --host {1} --port {2}' -f $runner, $ListenAddress, $Port
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    if ($existing.Actions.Count -ne 1 -or
        $existing.Actions[0].Execute -ne $pythonWindowless -or
        $existing.Actions[0].Arguments -ne $arguments -or
        $existing.Actions[0].WorkingDirectory -ne $projectRoot) {
        throw "Task NEF-Expo already exists with different settings. Inspect it before changing it."
    }
    if ($existing.State -eq "Running") {
        Write-Output "NEF-Expo is already running. No process was restarted."
        return
    }
}
$listener = @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
    Where-Object { $_.LocalPort -eq $Port })
if ($listener.Count) {
    throw "Port $Port is already occupied. Verify and stop its owner before starting NEF-Expo."
}

$account = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $pythonWindowless `
    -Argument $arguments -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $account
$principal = New-ScheduledTaskPrincipal -UserId $account `
    -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings `
    -Description "Local NEF server. Starts at user logon, independent of Codex." `
    -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Output "Windows task NEF-Expo started. URL: http://127.0.0.1:$Port/"
Write-Output "Logs: $projectRoot\.runtime\nef-background.stdout.log / nef-background.stderr.log"
