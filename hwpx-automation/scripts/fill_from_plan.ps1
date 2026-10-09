param(
  [Parameter(Mandatory = $true)][string]$PlanPath
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Import-Module (Join-Path $scriptDir 'AutoHwp.psm1') -Force -DisableNameChecking

$planFullPath = Resolve-AutoHwpPath $PlanPath
$planDir = Split-Path -Parent $planFullPath
$plan = Get-Content -LiteralPath $planFullPath -Encoding UTF8 | ConvertFrom-Json

function Resolve-PlanPath {
  param([Parameter(Mandatory = $true)][string]$Path)
  if ([System.IO.Path]::IsPathRooted($Path)) {
    return [System.IO.Path]::GetFullPath($Path)
  }
  return [System.IO.Path]::GetFullPath((Join-Path $planDir $Path))
}

$templatePath = Resolve-PlanPath $plan.template
$outputPath = Resolve-PlanPath $plan.output
$outputDir = Split-Path -Parent $outputPath
if ($outputDir) { New-Item -ItemType Directory -Force -Path $outputDir | Out-Null }

Copy-Item -LiteralPath $templatePath -Destination $outputPath -Force

$hwp = $null
try {
  $hwp = New-HwpAutomation
  Open-HwpDocument $hwp $outputPath | Out-Null

  foreach ($operation in $plan.operations) {
    Invoke-HwpFillOperation $hwp $operation
  }

  Save-HwpDocumentAs $hwp $outputPath | Out-Null
  $plainText = Get-HwpPlainText $hwp

  $missing = @()
  foreach ($expected in @($plan.verify.must_contain)) {
    if ($plainText -notlike "*$expected*") { $missing += $expected }
  }

  $forbiddenFound = @()
  foreach ($forbidden in @($plan.verify.must_not_contain)) {
    if ($plainText -like "*$forbidden*") { $forbiddenFound += $forbidden }
  }

  $verifyPath = $null
  if ($plan.verify.text_output) {
    $verifyPath = Resolve-PlanPath $plan.verify.text_output
    $verifyDir = Split-Path -Parent $verifyPath
    if ($verifyDir) { New-Item -ItemType Directory -Force -Path $verifyDir | Out-Null }
    Set-Content -LiteralPath $verifyPath -Value $plainText -Encoding UTF8
  }

  $result = [ordered]@{
    output = $outputPath
    verify_text = $verifyPath
    missing = $missing
    forbidden_found = $forbiddenFound
    ok = ($missing.Count -eq 0 -and $forbiddenFound.Count -eq 0)
  }
  $result | ConvertTo-Json -Depth 5

  if (-not $result.ok) {
    exit 2
  }
}
finally {
  Close-HwpAutomation $hwp
}

