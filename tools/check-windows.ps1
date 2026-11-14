# A Windows-compatible subset; the full preflight/native/Swift build runs in CI.
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$python = Join-Path $repoRoot '.venv/Scripts/python.exe'
$gitRoot = Split-Path (Split-Path (Get-Command git).Source -Parent) -Parent
$bash = Join-Path $gitRoot 'bin/bash.exe'
if (-not (Test-Path $python)) { throw 'Run tools/setup-windows.ps1 first.' }
if (-not (Test-Path $bash)) { throw 'Git for Windows with Git Bash is required.' }
$failed = @()
$oldUtf8 = $env:PYTHONUTF8
Push-Location $repoRoot
try {
    $env:PYTHONUTF8 = '1'
    New-Item -ItemType Directory -Force '.local/checks' | Out-Null
    $pins = git submodule status --recursive
    if ($LASTEXITCODE -ne 0 -or $pins -match '^[-+U]') { throw 'Submodules are missing or differ from the pinned commits.' }
    foreach ($check in @(
        'check-ci-component-keys', 'check-game-deps', 'check-wine-media-dlls',
        'check-font-keys-repair', 'check-nls-extra-switch', 'check-config-catalog',
        'check-translations', 'check-doc-links'
    )) {
        & $python "tests/host/$check.py" *> ".local/checks/$check.log"
        if ($LASTEXITCODE -ne 0) { $failed += $check; Write-Host "FAIL $check (see .local/checks/$check.log)" }
        else { Write-Host "PASS $check" }
    }
    & $bash tools/check-prefix-template.sh *> '.local/checks/prefix-template.log'
    if ($LASTEXITCODE -ne 0) { $failed += 'prefix-template' }
    else { Write-Host 'PASS prefix-template' }

    # Exercise the installed hook through Git, without contacting any remote.
    $hookCases = @(
        @('origin', 'https://github.com/kinghuijae/Madeira.git', 0),
        @('origin', 'git@github.com:kinghuijae/Madeira.git', 0),
        @('upstream', 'DISABLED', 1),
        @('renamed', 'https://github.com/willfaust/Madeira.git', 1),
        @('renamed', 'git@github.com:willfaust/Madeira.git', 1),
        @('renamed', 'ssh://git@github.com/willfaust/Madeira.git', 1),
        @('renamed', 'ssh://git@ssh.github.com:443/willfaust/Madeira.git', 1),
        @('renamed', 'https://github.com:443/willfaust/Madeira.git', 1),
        @('renamed', 'https://github.com/WILLFAUST/MADEIRA.git/', 1),
        @('renamed', 'https://github.com/willfaust/wine.git', 1)
    )
    # PowerShell 5.1 treats redirected native stderr as an ErrorRecord, including
    # the expected rejection message. Judge these calls by their exit code.
    $oldErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        foreach ($case in $hookCases) {
            '' | git hook run pre-push -- $case[0] $case[1] 2> '.local/checks/pre-push.log'
            if ($LASTEXITCODE -ne $case[2]) { $failed += "pre-push: $($case[1])" }
        }
    } finally {
        $ErrorActionPreference = $oldErrorAction
    }
    if (-not ($failed -match '^pre-push')) { Write-Host "PASS pre-push ($($hookCases.Count) destinations)" }
    $scripts = @(git ls-files 'tools/*.sh' 'tools/build/*.sh') + @('.githooks/pre-push')
    foreach ($script in $scripts) {
        & $bash -n $script
        if ($LASTEXITCODE -ne 0) { $failed += "shell syntax: $script" }
    }
    if (-not ($failed -match '^shell syntax')) { Write-Host "PASS shell syntax ($($scripts.Count) scripts)" }
    if ($failed.Count) { throw "Failed checks: $($failed -join ', ')" }
    Write-Host 'Windows checks passed. Swift type-check, POSIX fixtures, Xcode/IPA and device tests remain separate.'
} finally {
    $env:PYTHONUTF8 = $oldUtf8
    Pop-Location
}
