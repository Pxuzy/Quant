param(
    [ValidateSet("start", "start-bg", "restart", "status", "smoke", "logs", "stop")]
    [string]$Command = "start",
    [int]$ApiPort = 8021,
    [int]$WebPort = 5175,
    [int]$WaitSeconds = 45,
    [int]$LogLines = 80,
    [switch]$SkipApi,
    [switch]$SkipWeb,
    [switch]$ForcePortOwner
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$apiDir = Join-Path $root "quant"
$webDir = Join-Path $root "apps\web"
$storageDir = Join-Path $root "storage"
$apiPython = Join-Path $apiDir ".venv\Scripts\python.exe"
$apiScript = Join-Path $apiDir "scripts\run_api_server.py"
$apiUrl = "http://127.0.0.1:$ApiPort/health"
$webBaseUrl = "http://127.0.0.1:$WebPort"
$webUrl = "$webBaseUrl/data-system/data-sources"
$webEntryUrl = "$webBaseUrl/src/main.tsx"
$webPidPath = Join-Path $storageDir "web-$WebPort.pid"
$apiPidPath = Join-Path $storageDir "api-$ApiPort.pid"
$webOutLog = Join-Path $storageDir "web-$WebPort.out.log"
$webErrLog = Join-Path $storageDir "web-$WebPort.err.log"
$apiLog = Join-Path $storageDir "api-$ApiPort.log"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Warn([string]$Message) {
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Test-HttpOk([string]$Url, [int]$TimeoutSeconds = 5) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec $TimeoutSeconds
        return [int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 400
    } catch {
        return $false
    }
}

function Test-WebReady([int]$TimeoutSeconds = 5) {
    if (!(Test-HttpOk $webUrl $TimeoutSeconds)) {
        return $false
    }
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $webEntryUrl -TimeoutSec $TimeoutSeconds
        if ([int]$response.StatusCode -lt 200 -or [int]$response.StatusCode -ge 400) {
            return $false
        }
        $contentType = [string]$response.Headers["Content-Type"]
        $content = [string]$response.Content
        if ($contentType -match "text/html" -and $content -match "Internal Server Error|spawn EPERM|ErrorOverlay") {
            return $false
        }
        return $true
    } catch {
        return $false
    }
}

function Wait-Http([string]$Url, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-HttpOk $Url 5) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Test-ProcessRunning([int]$ProcessIdValue) {
    if ($ProcessIdValue -le 0) {
        return $false
    }
    return $null -ne (Get-Process -Id $ProcessIdValue -ErrorAction SilentlyContinue)
}

function Get-ListeningProcessId([int]$Port) {
    $lines = netstat -ano -p tcp
    foreach ($line in $lines) {
        $parts = $line -split "\s+" | Where-Object { $_ }
        if ($parts.Count -lt 5) {
            continue
        }
        if ($parts[0] -ne "TCP" -or $parts[3] -ne "LISTENING") {
            continue
        }
        if ($parts[1] -match ":$Port$") {
            return [int]$parts[4]
        }
    }
    return $null
}

function Get-ProcessCommandLine([int]$ProcessIdValue) {
    try {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessIdValue" -ErrorAction Stop
        return $process.CommandLine
    } catch {
        return ""
    }
}

function Get-ManagedLabel([int]$OwnerProcessId, [int]$ManagedProcessId) {
    if (!$OwnerProcessId) {
        return "none"
    }
    if ($ManagedProcessId -and $OwnerProcessId -eq $ManagedProcessId) {
        return "managed"
    }
    if ($ManagedProcessId -and (Test-ProcessRunning $ManagedProcessId)) {
        return "managed-listener"
    }
    return "unmanaged"
}

function Read-ManagedWebProcessId {
    try {
        $rawValue = (Get-Content -Raw -LiteralPath $webPidPath -ErrorAction Stop).Trim()
        if ($rawValue) {
            return [int]$rawValue
        }
    } catch {
        return $null
    }
    return $null
}

function Read-ManagedApiProcessId {
    try {
        $rawValue = (Get-Content -Raw -LiteralPath $apiPidPath -ErrorAction Stop).Trim()
        if ($rawValue) {
            return [int]$rawValue
        }
    } catch {
        return $null
    }
    return $null
}

function Remove-ManagedWebPidFile {
    if (Test-Path $webPidPath) {
        Remove-Item -LiteralPath $webPidPath -Force
    }
}

function Remove-ManagedApiPidFile {
    if (Test-Path $apiPidPath) {
        Remove-Item -LiteralPath $apiPidPath -Force
    }
}

function Test-NodeSpawn {
    Push-Location $webDir
    try {
        $script = "const cp=require('node:child_process');const r=cp.spawnSync('cmd.exe',['/c','echo','ok'],{encoding:'utf8'});if(r.error){console.error(String(r.error));process.exit(1)}"
        & node -e $script *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    } finally {
        Pop-Location
    }
}

function Invoke-ApiRunner([string]$RunnerCommand, [int]$Wait = 30) {
    if (!(Test-Path $apiPython)) {
        throw "API virtualenv not found: $apiPython"
    }
    if (!(Test-Path $apiScript)) {
        throw "API runner not found: $apiScript"
    }
    Push-Location $apiDir
    try {
        $env:QUANT_API_PORT = [string]$ApiPort
        if ($RunnerCommand -eq "start") {
            & $apiPython $apiScript start --wait $Wait
        } else {
            & $apiPython $apiScript $RunnerCommand
        }
    } finally {
        Pop-Location
    }
}

function Start-Api {
    if ($SkipApi) {
        Write-Warn "API start skipped."
        return
    }
    Write-Step "Starting API on $apiUrl"
    Invoke-ApiRunner "start" $WaitSeconds
}

function Stop-Api {
    $managedProcessId = Read-ManagedApiProcessId
    if ($managedProcessId -and (Test-ProcessRunning $managedProcessId)) {
        Write-Step "Stopping managed API process pid=$managedProcessId"
        Invoke-ApiRunner "stop" 0
    } else {
        Remove-ManagedApiPidFile
    }

    $ownerProcessId = Get-ListeningProcessId $ApiPort
    if ($ownerProcessId -and $ForcePortOwner) {
        Write-Step "Stopping unmanaged API port owner pid=$ownerProcessId"
        taskkill /PID $ownerProcessId /T /F | Out-Null
        if ($LASTEXITCODE -ne 0 -or (Test-ProcessRunning $ownerProcessId)) {
            Write-Warn "Could not stop API port owner pid=$ownerProcessId. Run from an elevated terminal if this process must be stopped."
            return
        }
        Write-Ok "API port owner stopped."
        return
    }
    if ($ownerProcessId) {
        Write-Warn "API port $ApiPort is owned by unmanaged pid=$ownerProcessId. Use '-ForcePortOwner' only if you want this script to kill it."
        return
    }
    Write-Ok "API was not running on port $ApiPort."
}

function Start-WebBackground {
    if ($SkipWeb) {
        Write-Warn "Web start skipped."
        return
    }
    if (!(Test-Path (Join-Path $webDir "package.json"))) {
        throw "Frontend package.json not found: $webDir"
    }
    if (Test-WebReady 5) {
        $ownerProcessId = Get-ListeningProcessId $WebPort
        Write-Ok "Web already responds at $webUrl"
        if ($ownerProcessId) {
            Write-Host "     port owner pid=$ownerProcessId"
        }
        return
    }
    if (!(Test-NodeSpawn)) {
        Write-Warn "Node child_process spawn check failed. If Vite reports 'spawn EPERM', Windows is blocking Node from spawning helpers."
    }

    New-Item -ItemType Directory -Force -Path $storageDir | Out-Null
    Remove-Item -LiteralPath $webOutLog -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $webErrLog -Force -ErrorAction SilentlyContinue

    Write-Step "Starting Web in background on $webUrl"
    Push-Location $webDir
    try {
        $env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$ApiPort"
        $env:VITE_DEV_SERVER_PORT = [string]$WebPort
        $cmdOutput = "npm run dev -- --host 127.0.0.1 --port $WebPort --strictPort 1> `"$webOutLog`" 2> `"$webErrLog`""
        $arguments = @(
            "/d",
            "/c",
            $cmdOutput
        )
        $process = Start-Process `
            -FilePath "cmd.exe" `
            -ArgumentList $arguments `
            -WorkingDirectory $webDir `
            -WindowStyle Hidden `
            -PassThru
        Set-Content -LiteralPath $webPidPath -Value ([string]$process.Id) -Encoding UTF8
    } finally {
        Pop-Location
    }

    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-WebReady 5) {
            break
        }
        Start-Sleep -Milliseconds 500
    }
    if (!(Test-WebReady 5)) {
        Show-Logs
        throw "Web did not become ready at $webUrl"
    }
    Write-Ok "Web ready at $webUrl"
}

function Start-WebForeground {
    if ($SkipWeb) {
        Write-Warn "Web start skipped."
        return
    }
    if (!(Test-Path (Join-Path $webDir "package.json"))) {
        throw "Frontend package.json not found: $webDir"
    }
    if (Test-WebReady 5) {
        $ownerProcessId = Get-ListeningProcessId $WebPort
        Write-Ok "Web already responds at $webUrl"
        if ($ownerProcessId) {
            Write-Host "     port owner pid=$ownerProcessId"
        }
        return
    }
    if (!(Test-NodeSpawn)) {
        Write-Warn "Node child_process spawn check failed. If Vite reports 'spawn EPERM', Windows is blocking Node from spawning helpers."
    }

    Write-Step "Starting Web in foreground on $webUrl"
    Push-Location $webDir
    try {
        $env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$ApiPort"
        $env:VITE_DEV_SERVER_PORT = [string]$WebPort
        Write-Host "Vite will keep this terminal occupied. Press Ctrl+C to stop it." -ForegroundColor DarkGray
        npm run dev -- --host 127.0.0.1 --port $WebPort --strictPort
    } finally {
        Pop-Location
    }
}

function Stop-Web {
    $managedProcessId = Read-ManagedWebProcessId
    if ($managedProcessId -and (Test-ProcessRunning $managedProcessId)) {
        Write-Step "Stopping managed Web process pid=$managedProcessId"
        taskkill /PID $managedProcessId /T /F | Out-Null
        Remove-ManagedWebPidFile
        Write-Ok "Managed Web process stopped."
        return
    }
    Remove-ManagedWebPidFile

    $ownerProcessId = Get-ListeningProcessId $WebPort
    if ($ownerProcessId -and $ForcePortOwner) {
        Write-Step "Stopping unmanaged Web port owner pid=$ownerProcessId"
        taskkill /PID $ownerProcessId /T /F | Out-Null
        if ($LASTEXITCODE -ne 0 -or (Test-ProcessRunning $ownerProcessId)) {
            Write-Warn "Could not stop Web port owner pid=$ownerProcessId. Run from an elevated terminal if this process must be stopped."
            return
        }
        Write-Ok "Web port owner stopped."
        return
    }
    if ($ownerProcessId) {
        Write-Warn "Web port $WebPort is owned by unmanaged pid=$ownerProcessId. Use 'stop -ForcePortOwner' only if you want this script to kill it."
        return
    }
    Write-Ok "Web was not running on port $WebPort."
}

function Invoke-Json([string]$Url, [int]$TimeoutSeconds = 15) {
    try {
        return Invoke-RestMethod -Uri $Url -TimeoutSec $TimeoutSeconds
    } catch {
        throw "GET $Url failed: $($_.Exception.Message)"
    }
}

function Normalize-Array($Value) {
    if ($null -eq $Value) {
        return @()
    }
    if ($Value -is [System.Array]) {
        return @($Value | ForEach-Object { $_ })
    }
    return @($Value)
}

function Assert-Field($Object, [string]$FieldName, [string]$Context) {
    if ($null -eq $Object) {
        throw "$Context is empty."
    }
    $property = $Object.PSObject.Properties | Where-Object { $_.Name -eq $FieldName } | Select-Object -First 1
    if ($null -eq $property -or $null -eq $property.Value -or $property.Value -eq "") {
        throw "$Context missing field '$FieldName'."
    }
}

function Invoke-Smoke {
    Write-Step "Running local smoke checks"
    $health = Invoke-Json $apiUrl 10
    Assert-Field $health "status" "health"
    Write-Ok "API health status=$($health.status)"

    $databaseStatus = Invoke-Json "http://127.0.0.1:$ApiPort/api/database/status" 15
    Assert-Field $databaseStatus "database_kind" "database status"
    Assert-Field $databaseStatus "data_lake_path" "database status"
    Assert-Field $databaseStatus "duckdb_engine_status" "database status"
    Write-Ok "database kind=$($databaseStatus.database_kind), duckdb=$($databaseStatus.duckdb_engine_status)"

    $overview = Invoke-Json "http://127.0.0.1:$ApiPort/api/database/integration-overview?market=A_SHARE" 20
    Assert-Field $overview "summary" "integration overview"
    Assert-Field $overview "dataset_snapshots" "integration overview"
    $snapshots = Normalize-Array $overview.dataset_snapshots
    if ($snapshots.Count -eq 0) {
        throw "integration overview has no dataset snapshots."
    }
    $snapshotNames = ($snapshots | ForEach-Object { "$($_.dataset_name):rows=$($_.row_count):schema=$($_.schema_fields_count)" }) -join ", "
    Write-Ok "datasets $snapshotNames"
    Write-Ok "latest_data_date=$($overview.summary.latest_data_date), recent_batches=$($overview.summary.recent_batches_total)"

    $sources = Normalize-Array (Invoke-Json "http://127.0.0.1:$ApiPort/api/data-sources" 20)
    if ($sources.Count -eq 0) {
        throw "data sources list is empty."
    }
    foreach ($source in $sources) {
        Assert-Field $source "code" "data source"
        Assert-Field $source "health_status" "data source $($source.code)"
        Assert-Field $source "capabilities" "data source $($source.code)"
        Assert-Field $source "provider_metadata" "data source $($source.code)"
    }
    $sourceSummary = ($sources | ForEach-Object {
        $smoke = $_.config_json.last_smoke_test
        $smokeStatus = if ($smoke) { $smoke.status } else { "no-smoke" }
        "$($_.code):health=$($_.health_status):smoke=$smokeStatus"
    }) -join ", "
    Write-Ok "providers $sourceSummary"

    if (!(Test-WebReady 10)) {
        throw "Web page did not respond at $webUrl"
    }
    Write-Ok "Web page and entry module respond at $webUrl"
}

function Show-Logs {
    Write-Step "Log paths"
    Write-Host "API: $apiLog"
    Write-Host "Web stdout: $webOutLog"
    Write-Host "Web stderr: $webErrLog"

    if (Test-Path $apiLog) {
        Write-Step "API log tail"
        Get-Content -LiteralPath $apiLog -Tail $LogLines -ErrorAction SilentlyContinue
    }
    if (Test-Path $webOutLog) {
        Write-Step "Web stdout tail"
        Get-Content -LiteralPath $webOutLog -Tail $LogLines -ErrorAction SilentlyContinue
    }
    if (Test-Path $webErrLog) {
        Write-Step "Web stderr tail"
        Get-Content -LiteralPath $webErrLog -Tail $LogLines -ErrorAction SilentlyContinue
    }
}

function Show-Status {
    Write-Step "API status"
    Invoke-ApiRunner "status" 0
    $apiOwnerProcessId = Get-ListeningProcessId $ApiPort
    $managedApiProcessId = Read-ManagedApiProcessId
    if ($apiOwnerProcessId) {
        $apiManagedLabel = Get-ManagedLabel $apiOwnerProcessId $managedApiProcessId
        Write-Host "port owner: pid=$apiOwnerProcessId ($apiManagedLabel)"
        if ($managedApiProcessId) {
            Write-Host "managed launcher pid file: $apiPidPath -> $managedApiProcessId"
        }
    } else {
        Write-Host "port owner: none"
    }

    Write-Step "Web status"
    $webHealthy = Test-WebReady 5
    $ownerProcessId = Get-ListeningProcessId $WebPort
    $managedProcessId = Read-ManagedWebProcessId
    if ($webHealthy) {
        Write-Host "running; healthy status=ok; url=$webUrl"
    } else {
        Write-Host "stopped or not ready; url=$webUrl"
    }
    if ($ownerProcessId) {
        $managedLabel = Get-ManagedLabel $ownerProcessId $managedProcessId
        Write-Host "port owner: pid=$ownerProcessId ($managedLabel)"
        $commandLine = Get-ProcessCommandLine $ownerProcessId
        if ($commandLine) {
            Write-Host "command: $commandLine"
        }
    } else {
        Write-Host "port owner: none"
    }
    if ($managedProcessId) {
        Write-Host "managed pid file: $webPidPath -> $managedProcessId"
    }
    Write-Host "logs: $webOutLog ; $webErrLog"
}

function Start-Stack([bool]$Background) {
    Start-Api
    if ($Background) {
        Start-WebBackground
        Show-Status
        return
    }
    Start-WebForeground
}

switch ($Command) {
    "start" {
        Start-Stack $false
    }
    "start-bg" {
        Start-Stack $true
    }
    "restart" {
        if (!$SkipWeb) {
            Stop-Web
        }
        if (!$SkipApi) {
            Stop-Api
        }
        Start-Stack $true
    }
    "status" {
        Show-Status
    }
    "smoke" {
        Invoke-Smoke
    }
    "logs" {
        Show-Logs
    }
    "stop" {
        if (!$SkipWeb) {
            Stop-Web
        }
        if (!$SkipApi) {
            Stop-Api
        }
    }
}
