Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $ProjectRoot "logs"
$LogFile = Join-Path $LogDir "pipeline.log"
$DockerExe = "docker"
$DockerCliPath = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
$ArchiveDelayDays = 5

if (Test-Path $DockerCliPath) {
    $DockerExe = $DockerCliPath
}

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

function Write-PipelineLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Value "[$timestamp] $Message"
}

function Invoke-LoggedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [string[]]$Arguments = @()
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $FilePath @Arguments 2>&1 | ForEach-Object {
            Add-Content -Path $LogFile -Value $_
        }
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    return $LASTEXITCODE
}

function Test-DockerEngine {
    $quotedDockerExe = '"' + $DockerExe + '"'
    & $env:ComSpec /c "$quotedDockerExe info >nul 2>nul"
    return $LASTEXITCODE -eq 0
}

function Wait-DockerEngine {
    if (Test-DockerEngine) {
        Write-PipelineLog "Docker Desktop engine san sang"
        return $true
    }

    $dockerDesktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerDesktop) {
        Write-PipelineLog "Docker Desktop chua san sang, thu khoi dong Docker Desktop"
        Start-Process -FilePath $dockerDesktop
    } else {
        Write-PipelineLog "Docker Desktop chua san sang va khong tim thay Docker Desktop.exe"
    }

    for ($attempt = 1; $attempt -le 24; $attempt++) {
        Start-Sleep -Seconds 5
        if (Test-DockerEngine) {
            Write-PipelineLog "Docker Desktop engine san sang"
            return $true
        }
        Write-PipelineLog "Cho Docker Desktop san sang... attempt=$attempt/24"
    }

    Write-PipelineLog "Docker Desktop van chua san sang sau khi cho. Dung pipeline."
    return $false
}

function Test-TcpPort {
    param(
        [Parameter(Mandatory = $true)]
        [string]$HostName,
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(2000, $false)) {
            return $false
        }

        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Wait-PostgresConnection {
    param(
        [Parameter(Mandatory = $true)]
        [string]$HostName,
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    for ($attempt = 1; $attempt -le 12; $attempt++) {
        if (Test-TcpPort -HostName $HostName -Port $Port) {
            Write-PipelineLog "PostgreSQL host port san sang: ${HostName}:${Port}"
            return $true
        }

        Write-PipelineLog "Cho PostgreSQL host port ${HostName}:${Port}... attempt=$attempt/12"
        Start-Sleep -Seconds 5
    }

    Write-PipelineLog "PostgreSQL healthy nhung host port ${HostName}:${Port} chua san sang. Dung pipeline."
    return $false
}

function Get-ArchiveTargetDate {
    $timeZone = [System.TimeZoneInfo]::FindSystemTimeZoneById("SE Asia Standard Time")
    $todayLocal = [System.TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $timeZone).Date
    return $todayLocal.AddDays(-$ArchiveDelayDays).ToString("yyyy-MM-dd")
}

try {
    Set-Location $ProjectRoot
    Write-PipelineLog "Bat dau pipeline tu Task Scheduler PowerShell"
    Write-PipelineLog "Docker CLI: $DockerExe"

    if ([string]::IsNullOrWhiteSpace($env:DB_HOST) -or $env:DB_HOST -eq "localhost") {
        $env:DB_HOST = "127.0.0.1"
    }
    if ([string]::IsNullOrWhiteSpace($env:DB_PORT)) {
        $env:DB_PORT = "5432"
    }
    Write-PipelineLog "DB host cho scheduled run: $env:DB_HOST"

    if (-not (Wait-DockerEngine)) {
        exit 1
    }

    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $legacyVenvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"
    $pipelinePython = ""
    [string[]]$pipelinePythonPrefixArguments = @()

    if (Test-Path $venvPython) {
        $pipelinePython = $venvPython
    } elseif (Test-Path $legacyVenvPython) {
        $pipelinePython = $legacyVenvPython
    } else {
        $pipelinePython = "uv"
        $pipelinePythonPrefixArguments = @("--cache-dir", ".uv-cache", "run", "python")
    }

    Write-PipelineLog "Kiem tra PostgreSQL Docker container"
    $composeExit = Invoke-LoggedCommand -FilePath $DockerExe -Arguments @("compose", "up", "-d")
    if ($composeExit -ne 0) {
        Write-PipelineLog "Khong the khoi dong PostgreSQL bang docker compose. Kiem tra Docker Desktop."
        exit $composeExit
    }

    $postgresReady = $false
    for ($attempt = 1; $attempt -le 12; $attempt++) {
        $health = ""
        try {
            $health = & $DockerExe inspect --format="{{.State.Health.Status}}" weather_postgres 2>$null
        } catch {
            $health = ""
        }

        if ($health -eq "healthy") {
            $postgresReady = $true
            break
        }

        Write-PipelineLog "Cho PostgreSQL healthy... current=$health"
        Start-Sleep -Seconds 5
    }

    if (-not $postgresReady) {
        Write-PipelineLog "PostgreSQL chua healthy sau khi cho. Dung pipeline."
        exit 1
    }

    Write-PipelineLog "PostgreSQL healthy, kiem tra host port truoc khi chay ETL"

    if (-not (Wait-PostgresConnection -HostName $env:DB_HOST -Port ([int]$env:DB_PORT))) {
        exit 1
    }

    $targetDate = Get-ArchiveTargetDate
    Write-PipelineLog "PostgreSQL healthy, backfill Archive API cho ngay da chac co du lieu: $targetDate"

    $backfillExit = Invoke-LoggedCommand -FilePath $pipelinePython -Arguments ($pipelinePythonPrefixArguments + @(
        "src\backfill_weather.py",
        "--start-date",
        $targetDate,
        "--end-date",
        $targetDate,
        "--sleep",
        "0.2"
    ))
    if ($backfillExit -ne 0) {
        Write-PipelineLog "Archive backfill that bai (exit=$backfillExit)"
        exit $backfillExit
    }

    Write-PipelineLog "Transform/load partition Archive target_date=$targetDate"
    $pipelineExit = Invoke-LoggedCommand -FilePath $pipelinePython -Arguments ($pipelinePythonPrefixArguments + @(
        "src\main.py",
        "--skip-extract",
        "--date",
        $targetDate,
        "--load"
    ))

    Write-PipelineLog "Ket thuc pipeline (exit=$pipelineExit)"
    exit $pipelineExit
} catch {
    Write-PipelineLog "Task Scheduler script loi: $($_.Exception.Message)"
    Write-PipelineLog "StackTrace: $($_.ScriptStackTrace)"
    exit 1
}
