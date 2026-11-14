# Configure this personal fork for editing/checks on Windows; IPA builds use macOS CI.
[CmdletBinding()]
param([switch]$SkipSubmodules, [switch]$SkipPython)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
function Invoke-Git {
    & git @args
    if ($LASTEXITCODE -ne 0) { throw "git failed: $args" }
}

Push-Location $repoRoot
$oldCache = $env:UV_CACHE_DIR
$oldPythonDir = $env:UV_PYTHON_INSTALL_DIR
try {
    $origin = Invoke-Git remote get-url origin
    if ($origin -notmatch '^https://github\.com/kinghuijae/Madeira(?:\.git)?/?$|^git@github\.com:kinghuijae/Madeira(?:\.git)?$') {
        throw "Expected origin to be kinghuijae/Madeira; found $origin"
    }
    $hooks = git config --local --get core.hooksPath
    $hookPath = (Join-Path $repoRoot '.githooks').Replace('\', '/')
    if ($hooks -and $hooks -ne '.githooks' -and $hooks -ne $hookPath) {
        throw "Another hooksPath is configured: $hooks. Integrate it before setup."
    }
    Invoke-Git config --local core.longpaths true
    Invoke-Git config --local core.autocrlf false
    Invoke-Git config --local core.hooksPath .githooks
    Invoke-Git config --local remote.pushDefault origin
    Invoke-Git config --local push.default simple
    if ('upstream' -notin @(Invoke-Git remote)) {
        Invoke-Git remote add upstream https://github.com/willfaust/Madeira.git
    }
    Invoke-Git config --local --replace-all remote.upstream.pushurl DISABLED

    if (-not $SkipSubmodules) {
        Invoke-Git -c core.longpaths=true -c core.autocrlf=false submodule update --init --recursive --depth 1 --jobs 4
    }
    # Submodule sources remain pinned. Disable their pushes until personal forks exist.
    $modules = @(Invoke-Git submodule foreach --quiet --recursive 'git rev-parse --show-toplevel')
    foreach ($module in $modules) {
        Invoke-Git -C $module config --local core.longpaths true
        Invoke-Git -C $module config --local core.autocrlf false
        Invoke-Git -C $module config --local core.hooksPath $hookPath
        Invoke-Git -C $module config --local --replace-all remote.origin.pushurl DISABLED
    }

    if (-not $SkipPython) {
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
            throw 'uv is required: install it from https://docs.astral.sh/uv/getting-started/installation/'
        }
        $env:UV_CACHE_DIR = Join-Path $repoRoot 'toolchains/uv-cache'
        $env:UV_PYTHON_INSTALL_DIR = Join-Path $repoRoot 'toolchains/python'
        & uv python install 3.12 --no-bin
        if ($LASTEXITCODE -ne 0) { throw 'Python installation failed' }
        if (-not (Test-Path '.venv/Scripts/python.exe')) {
            & uv venv --python 3.12 .venv
            if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
        }
        & ./.venv/Scripts/python.exe --version
        if ($LASTEXITCODE -ne 0) { throw 'Virtual environment is not usable' }
    }
    Write-Host 'Ready for Windows editing/checks. Run: .\tools\check-windows.ps1'
    Write-Host 'IPA build: GitHub Actions > Build IPA > Run workflow (macOS/Xcode).'
} finally {
    $env:UV_CACHE_DIR = $oldCache
    $env:UV_PYTHON_INSTALL_DIR = $oldPythonDir
    Pop-Location
}
