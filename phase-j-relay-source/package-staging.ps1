param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
$sourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent $sourceRoot
$files = @(
    (Join-Path $sourceRoot 'server.py'),
    (Join-Path $sourceRoot 'routeros.py'),
    (Join-Path $sourceRoot 'attestation-routers.example.json'),
    (Join-Path $sourceRoot 'scripts/validate_attestation_config.py'),
    (Join-Path $sourceRoot 'README.md')
)

foreach ($file in $files) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Required staging source file is missing: $file"
    }
}

$resolvedOutput = [System.IO.Path]::GetFullPath($OutputPath)
if (Test-Path -LiteralPath $resolvedOutput) {
    throw 'Output already exists; choose a new path so an existing artifact is preserved.'
}
$parent = Split-Path -Parent $resolvedOutput
if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}

Compress-Archive -LiteralPath $files -DestinationPath $resolvedOutput
Write-Output "Created staging source bundle: $resolvedOutput"
Write-Output 'Bundle excludes relay.env, relay.token, router credentials, and production configuration.'
