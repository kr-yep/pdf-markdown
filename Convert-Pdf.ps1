[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)][string]$Pdf,
    [string]$OutputDirectory,
    [string]$Pages,
    [switch]$FullPageOcr,
    [switch]$EnrichFormula,
    [ValidateRange(1, 32)][int]$Threads = 4,
    [ValidateRange(30, 14400)][int]$TimeoutSeconds = 1800
)
$ErrorActionPreference = 'Stop'
$pythonExe = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Docling environment missing; see README.md.' }
$convertArgs = @((Join-Path $PSScriptRoot 'convert_pdf.py'), $Pdf, '--threads', "$Threads", '--timeout-seconds', "$TimeoutSeconds")
if ($OutputDirectory) { $convertArgs += @('--output', $OutputDirectory) }
if ($Pages) { $convertArgs += @('--pages', $Pages) }
if ($FullPageOcr) { $convertArgs += '--full-page-ocr' }
if ($EnrichFormula) { $convertArgs += '--enrich-formula' }
& $pythonExe -X utf8 @convertArgs
if ($LASTEXITCODE -ne 0) { throw "PDF conversion failed (exit $LASTEXITCODE). Inspect the conversion receipt and log." }
