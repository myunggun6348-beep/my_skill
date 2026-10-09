param(
  [Parameter(Mandatory = $true)][string]$InputPath,
  [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Import-Module (Join-Path $scriptDir 'AutoHwp.psm1') -Force -DisableNameChecking

$inputFullPath = Resolve-AutoHwpPath $InputPath
$hwp = $null
try {
  $hwp = New-HwpAutomation
  Open-HwpDocument $hwp $inputFullPath | Out-Null
  $plainText = Get-HwpPlainText $hwp

  if ($OutputPath) {
    $outputFullPath = Resolve-AutoHwpPath $OutputPath
    $outputDir = Split-Path -Parent $outputFullPath
    if ($outputDir) { New-Item -ItemType Directory -Force -Path $outputDir | Out-Null }
    Set-Content -LiteralPath $outputFullPath -Value $plainText -Encoding UTF8
    $outputFullPath
  } else {
    $plainText
  }
}
finally {
  Close-HwpAutomation $hwp
}
