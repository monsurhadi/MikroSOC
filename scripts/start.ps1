$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    throw 'Create .venv and install requirements first. See SETUP.md.'
}
if (-not (Test-Path -LiteralPath 'config.json')) {
    throw 'Run .venv\Scripts\python.exe manage.py init first.'
}
$projectConfig = Get-Content -LiteralPath 'config.json' -Raw | ConvertFrom-Json
function Read-ProcessSecret([string]$Prompt) {
    $secureValue = Read-Host -Prompt $Prompt -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureValue)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}
try {
    if ($projectConfig.mode -eq 'live' -and $projectConfig.api_enabled) {
        $env:MIKROSOC_ROUTER_PASSWORD = Read-ProcessSecret 'Router reader password'
    }
    if ($projectConfig.response_enabled) {
        $env:MIKROSOC_RESPONSE_PASSWORD = Read-ProcessSecret 'Router responder password'
    }
    & '.\.venv\Scripts\python.exe' manage.py run
} finally {
    Remove-Item Env:\MIKROSOC_ROUTER_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:\MIKROSOC_RESPONSE_PASSWORD -ErrorAction SilentlyContinue
}
