param(
    [int]$ArchiveDelayDays = 5,
    [string]$TargetDate = "",
    [string]$TaskName = "WeatherPipeline",
    [int]$DockerWaitAttempts = 24,
    [int]$PostgresWaitAttempts = 12,
    [switch]$NoDockerDesktopStart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $ProjectRoot "logs"
$LogFile = Join-Path $LogDir "pipeline.log"
$RunStartedAt = Get-Date
$RunId = $RunStartedAt.ToString("yyyyMMdd-HHmmss")
$RunLogFile = Join-Path $LogDir "pipeline-$RunId.log"
$LockFile = Join-Path $LogDir "pipeline.lock"
$DockerExe = "docker"
$DockerCliPath = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
$script:LockStream = $null

if (Test-Path $DockerCliPath) {
    $DockerExe = $DockerCliPath
}

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

function Add-LogLine {
    param([string]$Line)
    Add-Content -Path $LogFile -Value $Line
    Add-Content -Path $RunLogFile -Value $Line
}

function Write-PipelineLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-LogLine "[$timestamp] $Message"
}

function Acquire-PipelineLock {
    try {
        $script:LockStream = [System.IO.File]::Open(
            $LockFile,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None
        )

        $writer = [System.IO.StreamWriter]::new($script:LockStream, [System.Text.Encoding]::UTF8, 1024, $true)
        $script:LockStream.SetLength(0)
        $writer.WriteLine("task=$TaskName")
        $writer.WriteLine("pid=$PID")
        $writer.WriteLine("started=$($RunStartedAt.ToString('o'))")
        $writer.Flush()
        $writer.Dispose()
        $script:LockStream.Flush()
        return $true
    } catch [System.IO.IOException] {
        Write-PipelineLog "Da co pipeline run khac dang chay. Bo qua run nay. Lock file: $LockFile"
        return $false
    }
}

function Release-PipelineLock {
    if ($null -ne $script:LockStream) {
        $script:LockStream.Dispose()
        $script:LockStream = $null
        Remove-Item -LiteralPath $LockFile -ErrorAction SilentlyContinue
    }
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
            Add-LogLine ([string]$_)
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
    if ((-not $NoDockerDesktopStart) -and (Test-Path $dockerDesktop)) {
        Write-PipelineLog "Docker Desktop chua san sang, thu khoi dong Docker Desktop"
        Start-Process -FilePath $dockerDesktop
    } elseif ($NoDockerDesktopStart) {
        Write-PipelineLog "Docker Desktop chua san sang va NoDockerDesktopStart duoc bat"
    } else {
        Write-PipelineLog "Docker Desktop chua san sang va khong tim thay Docker Desktop.exe"
    }

    for ($attempt = 1; $attempt -le $DockerWaitAttempts; $attempt++) {
        Start-Sleep -Seconds 5
        if (Test-DockerEngine) {
            Write-PipelineLog "Docker Desktop engine san sang"
            return $true
        }
        Write-PipelineLog "Cho Docker Desktop san sang... attempt=$attempt/$DockerWaitAttempts"
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

    for ($attempt = 1; $attempt -le $PostgresWaitAttempts; $attempt++) {
        if (Test-TcpPort -HostName $HostName -Port $Port) {
            Write-PipelineLog "PostgreSQL host port san sang: ${HostName}:${Port}"
            return $true
        }

        Write-PipelineLog "Cho PostgreSQL host port ${HostName}:${Port}... attempt=$attempt/$PostgresWaitAttempts"
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

function Resolve-ArchiveTargetDate {
    if ([string]::IsNullOrWhiteSpace($TargetDate)) {
        return Get-ArchiveTargetDate
    }

    try {
        $parsed = [DateTime]::ParseExact(
            $TargetDate,
            "yyyy-MM-dd",
            [System.Globalization.CultureInfo]::InvariantCulture
        )
        return $parsed.ToString("yyyy-MM-dd")
    } catch {
        throw "TargetDate phai co format yyyy-MM-dd. Gia tri nhan duoc: $TargetDate"
    }
}

function Invoke-PipelineRun {
    Set-Location $ProjectRoot
    Write-PipelineLog "Bat dau pipeline tu Task Scheduler PowerShell task=$TaskName run_id=$RunId"
    Write-PipelineLog "Run log rieng: $RunLogFile"
    Write-PipelineLog "Docker CLI: $DockerExe"
    Write-PipelineLog "ArchiveDelayDays=$ArchiveDelayDays TargetDate=$TargetDate"

    if (-not (Acquire-PipelineLock)) {
        return 2
    }

    if ([string]::IsNullOrWhiteSpace($env:DB_HOST) -or $env:DB_HOST -eq "localhost") {
        $env:DB_HOST = "127.0.0.1"
    }
    if ([string]::IsNullOrWhiteSpace($env:DB_PORT)) {
        $env:DB_PORT = "5432"
    }
    Write-PipelineLog "DB host cho scheduled run: $env:DB_HOST"

    if (-not (Wait-DockerEngine)) {
        return 1
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
        return $composeExit
    }

    $postgresReady = $false
    for ($attempt = 1; $attempt -le $PostgresWaitAttempts; $attempt++) {
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

        Write-PipelineLog "Cho PostgreSQL healthy... attempt=$attempt/$PostgresWaitAttempts current=$health"
        Start-Sleep -Seconds 5
    }

    if (-not $postgresReady) {
        Write-PipelineLog "PostgreSQL chua healthy sau khi cho. Dung pipeline."
        return 1
    }

    Write-PipelineLog "PostgreSQL healthy, kiem tra host port truoc khi chay ETL"

    if (-not (Wait-PostgresConnection -HostName $env:DB_HOST -Port ([int]$env:DB_PORT))) {
        return 1
    }

    $targetDate = Resolve-ArchiveTargetDate
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
        return $backfillExit
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
    return $pipelineExit
}

$exitCode = 1
try {
    $exitCode = Invoke-PipelineRun
} catch {
    Write-PipelineLog "Task Scheduler script loi: $($_.Exception.Message)"
    Write-PipelineLog "StackTrace: $($_.ScriptStackTrace)"
    $exitCode = 1
} finally {
    Release-PipelineLock
}

exit $exitCode
