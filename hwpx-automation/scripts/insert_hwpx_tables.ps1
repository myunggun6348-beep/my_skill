param(
  [Parameter(Mandatory = $true)][string]$InputPath,
  [Parameter(Mandatory = $true)][string]$TableJsonPath,
  [string]$OutputPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $OutputPath) {
  $OutputPath = $InputPath
}

$modulePath = Join-Path $PSScriptRoot 'AutoHwp.psm1'
$populateScriptPath = Join-Path $PSScriptRoot 'populate_hwpx_table_cells.py'
Import-Module $modulePath -Force

$resolvedInputPath = Resolve-AutoHwpPath $InputPath
$resolvedTableJsonPath = Resolve-AutoHwpPath $TableJsonPath
$resolvedOutputPath = Resolve-AutoHwpPath $OutputPath

if ($resolvedInputPath -ne $resolvedOutputPath) {
  Copy-Item -LiteralPath $resolvedInputPath -Destination $resolvedOutputPath -Force
}

$tableSpec = Get-Content -Path $resolvedTableJsonPath -Raw -Encoding UTF8 | ConvertFrom-Json
$tables = @($tableSpec.tables)

[array]::Reverse($tables)

foreach ($table in $tables) {
  $hwp = New-HwpAutomation
  try {
    Open-HwpDocument -Hwp $hwp -Path $resolvedOutputPath | Out-Null
    Insert-HwpTableAtPlaceholder -Hwp $hwp -Placeholder ([string]$table.placeholder) -Rows ([object[]]$table.rows)
    Save-HwpDocumentAs -Hwp $hwp -Path $resolvedOutputPath | Out-Null
  }
  finally {
    Close-HwpAutomation $hwp
  }
}

& python $populateScriptPath --hwpx $resolvedOutputPath --table-json $resolvedTableJsonPath
if ($LASTEXITCODE -ne 0) {
  throw "Failed to populate table cell text in $resolvedOutputPath."
}
