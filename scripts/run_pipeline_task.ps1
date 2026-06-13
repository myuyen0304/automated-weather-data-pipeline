Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $ProjectRoot "logs"
$LogFile = Join-Path $LogDir "pipeline.log"
$DockerExe = "docker"
$DockerCliPath = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"

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

try {
    Set-Location $ProjectRoot
    Write-PipelineLog "Bat dau pipeline tu Task Scheduler PowerShell"
    Write-PipelineLog "Docker CLI: $DockerExe"

    if (-not (Wait-DockerEngine)) {
        exit 1
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

    Write-PipelineLog "PostgreSQL healthy, bat dau chay ETL"

    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $legacyVenvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"

    if (Test-Path $venvPython) {
        $pipelineExit = Invoke-LoggedCommand -FilePath $venvPython -Arguments @("src\main.py", "--load")
    } elseif (Test-Path $legacyVenvPython) {
        $pipelineExit = Invoke-LoggedCommand -FilePath $legacyVenvPython -Arguments @("src\main.py", "--load")
    } else {
        $pipelineExit = Invoke-LoggedCommand -FilePath "uv" -Arguments @("--cache-dir", ".uv-cache", "run", "python", "src\main.py", "--load")
    }

    Write-PipelineLog "Ket thuc pipeline (exit=$pipelineExit)"
    exit $pipelineExit
} catch {
    Write-PipelineLog "Task Scheduler script loi: $($_.Exception.Message)"
    Write-PipelineLog "StackTrace: $($_.ScriptStackTrace)"
    exit 1
}
