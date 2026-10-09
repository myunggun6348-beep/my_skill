Set-StrictMode -Version Latest

function New-HwpAutomation {
  $hwp = New-Object -ComObject HWPFrame.HwpObject
  try {
    $hwp.RegisterModule('FilePathCheckDLL', 'FilePathCheckerModule') | Out-Null
  } catch {
    Write-Warning "FilePathCheckDLL registration failed. Continuing may still work depending on HWP security settings. $_"
  }
  return $hwp
}

function Resolve-AutoHwpPath {
  param([Parameter(Mandatory = $true)][string]$Path)
  if ([System.IO.Path]::IsPathRooted($Path)) {
    return [System.IO.Path]::GetFullPath($Path)
  }
  return [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Path))
}

function Get-HwpDocumentFormat {
  param([Parameter(Mandatory = $true)][string]$Path)
  $extension = [System.IO.Path]::GetExtension($Path).ToLowerInvariant()
  switch ($extension) {
    '.hwpx' { return 'HWPX' }
    '.hwp' { return 'HWP' }
    default { return 'HWP' }
  }
}

function Open-HwpDocument {
  param(
    [Parameter(Mandatory = $true)]$Hwp,
    [Parameter(Mandatory = $true)][string]$Path
  )
  $fullPath = Resolve-AutoHwpPath $Path
  $format = Get-HwpDocumentFormat $fullPath
  $opened = $Hwp.Open($fullPath, $format, 'forceopen:true')
  if (-not $opened) {
    throw "Failed to open HWP document: $fullPath"
  }
  return $fullPath
}

function Save-HwpDocumentAs {
  param(
    [Parameter(Mandatory = $true)]$Hwp,
    [Parameter(Mandatory = $true)][string]$Path
  )
  $fullPath = Resolve-AutoHwpPath $Path
  $dir = Split-Path -Parent $fullPath
  if ($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  $format = Get-HwpDocumentFormat $fullPath
  $Hwp.SaveAs($fullPath, $format, '') | Out-Null
  return $fullPath
}

function Close-HwpAutomation {
  param($Hwp)
  if ($null -ne $Hwp) {
    try { $Hwp.Quit() | Out-Null } catch { }
  }
}

function Invoke-HwpAllReplace {
  param(
    [Parameter(Mandatory = $true)]$Hwp,
    [Parameter(Mandatory = $true)][string]$Find,
    [AllowEmptyString()][string]$Replace = ''
  )
  $Hwp.HAction.GetDefault('AllReplace', $Hwp.HParameterSet.HFindReplace.HSet) | Out-Null
  $Hwp.HParameterSet.HFindReplace.FindString = $Find
  $Hwp.HParameterSet.HFindReplace.ReplaceString = $Replace
  $Hwp.HParameterSet.HFindReplace.Direction = 0
  $Hwp.HParameterSet.HFindReplace.IgnoreMessage = 1
  return $Hwp.HAction.Execute('AllReplace', $Hwp.HParameterSet.HFindReplace.HSet)
}

function Move-HwpDocBegin {
  param([Parameter(Mandatory = $true)]$Hwp)
  $Hwp.Run('MoveDocBegin') | Out-Null
}

function Move-HwpDocEnd {
  param([Parameter(Mandatory = $true)]$Hwp)
  $Hwp.Run('MoveDocEnd') | Out-Null
}

function Find-HwpNextText {
  param(
    [Parameter(Mandatory = $true)]$Hwp,
    [Parameter(Mandatory = $true)][string]$Find
  )
  $Hwp.HAction.GetDefault('RepeatFind', $Hwp.HParameterSet.HFindReplace.HSet) | Out-Null
  $Hwp.HParameterSet.HFindReplace.FindString = $Find
  $Hwp.HParameterSet.HFindReplace.Direction = 0
  $Hwp.HParameterSet.HFindReplace.IgnoreMessage = 1
  return $Hwp.HAction.Execute('RepeatFind', $Hwp.HParameterSet.HFindReplace.HSet)
}

function Replace-HwpCurrentSelection {
  param(
    [Parameter(Mandatory = $true)]$Hwp,
    [AllowEmptyString()][string]$Text = ''
  )
  $Hwp.HAction.GetDefault('InsertText', $Hwp.HParameterSet.HInsertText.HSet) | Out-Null
  $Hwp.HParameterSet.HInsertText.Text = $Text
  return $Hwp.HAction.Execute('InsertText', $Hwp.HParameterSet.HInsertText.HSet)
}

function Replace-HwpNthText {
  param(
    [Parameter(Mandatory = $true)]$Hwp,
    [Parameter(Mandatory = $true)][string]$Find,
    [Parameter(Mandatory = $true)][int]$Occurrence,
    [AllowEmptyString()][string]$Text = ''
  )
  if ($Occurrence -lt 1) { throw 'Occurrence must be >= 1.' }
  Move-HwpDocBegin $Hwp
  for ($i = 1; $i -le $Occurrence; $i += 1) {
    $found = Find-HwpNextText $Hwp $Find
    if (-not $found) {
      throw "Could not find occurrence $Occurrence of '$Find'. Stopped at occurrence $i."
    }
  }
  Replace-HwpCurrentSelection $Hwp $Text | Out-Null
}


function Replace-HwpAfterSequence {
  param(
    [Parameter(Mandatory = $true)]$Hwp,
    [Parameter(Mandatory = $true)][string[]]$Sequence,
    [AllowEmptyString()][string]$Text = ''
  )
  if ($Sequence.Count -lt 1) { throw 'Sequence must contain at least one search string.' }
  Move-HwpDocBegin $Hwp
  foreach ($find in $Sequence) {
    $found = Find-HwpNextText $Hwp $find
    if (-not $found) {
      throw "Could not find sequence item '$find'."
    }
  }
  Replace-HwpCurrentSelection $Hwp $Text | Out-Null
}

function Insert-HwpIntoNextTableCellAfterSequence {
  param(
    [Parameter(Mandatory = $true)]$Hwp,
    [Parameter(Mandatory = $true)][string[]]$Sequence,
    [AllowEmptyString()][string]$Text = ''
  )
  if ($Sequence.Count -lt 1) { throw 'Sequence must contain at least one search string.' }
  Move-HwpDocBegin $Hwp
  foreach ($find in $Sequence) {
    $found = Find-HwpNextText $Hwp $find
    if (-not $found) {
      throw "Could not find sequence item '$find'."
    }
  }

  $Hwp.Run('MoveRight') | Out-Null
  $Hwp.FindCtrl() | Out-Null
  $Hwp.HAction.Run('ShapeObjTableSelCell') | Out-Null
  Replace-HwpCurrentSelection $Hwp $Text | Out-Null
}

function Insert-HwpTextAtEnd {
  param(
    [Parameter(Mandatory = $true)]$Hwp,
    [AllowEmptyString()][string]$Text = ''
  )
  Move-HwpDocEnd $Hwp
  Replace-HwpCurrentSelection $Hwp $Text | Out-Null
}

function New-HwpTableAtCursor {
  param(
    [Parameter(Mandatory = $true)]$Hwp,
    [Parameter(Mandatory = $true)][object[]]$Rows
  )
  $rowCount = $Rows.Count
  if ($rowCount -lt 1) {
    throw 'Table must contain at least one row.'
  }

  $colCount = 0
  foreach ($row in $Rows) {
    $cellCount = @($row).Count
    if ($cellCount -gt $colCount) {
      $colCount = $cellCount
    }
  }
  if ($colCount -lt 1) {
    throw 'Table must contain at least one column.'
  }

  $Hwp.HAction.GetDefault('TableCreate', $Hwp.HParameterSet.HTableCreation.HSet) | Out-Null
  $Hwp.HParameterSet.HTableCreation.Rows = $rowCount
  $Hwp.HParameterSet.HTableCreation.Cols = $colCount
  $Hwp.HParameterSet.HTableCreation.WidthType = 0
  $Hwp.HParameterSet.HTableCreation.HeightType = 0
  $created = $Hwp.HAction.Execute('TableCreate', $Hwp.HParameterSet.HTableCreation.HSet)
  if (-not $created) {
    throw "Failed to create a $rowCount x $colCount table."
  }
}

function Insert-HwpTableAtPlaceholder {
  param(
    [Parameter(Mandatory = $true)]$Hwp,
    [Parameter(Mandatory = $true)][string]$Placeholder,
    [Parameter(Mandatory = $true)][object[]]$Rows
  )
  Move-HwpDocBegin $Hwp
  $found = Find-HwpNextText $Hwp $Placeholder
  if (-not $found) {
    throw "Could not find table placeholder '$Placeholder'."
  }
  $Hwp.Run('Delete') | Out-Null
  New-HwpTableAtCursor $Hwp $Rows
}

function Get-HwpPlainText {
  param([Parameter(Mandatory = $true)]$Hwp)
  return $Hwp.GetTextFile('TEXT', '')
}

function Invoke-HwpFillOperation {
  param(
    [Parameter(Mandatory = $true)]$Hwp,
    [Parameter(Mandatory = $true)]$Operation
  )
  switch ($Operation.type) {
    'replace_all' {
      Invoke-HwpAllReplace $Hwp $Operation.find ([string]$Operation.text) | Out-Null
    }
    'replace_nth' {
      Replace-HwpNthText $Hwp $Operation.find ([int]$Operation.occurrence) ([string]$Operation.text)
    }
    'append_end' {
      Insert-HwpTextAtEnd $Hwp ([string]$Operation.text)
    }
    'replace_after_sequence' {
      Replace-HwpAfterSequence $Hwp ([string[]]$Operation.sequence) ([string]$Operation.text)
    }
    'insert_into_next_table_cell_after_sequence' {
      Insert-HwpIntoNextTableCellAfterSequence $Hwp ([string[]]$Operation.sequence) ([string]$Operation.text)
    }
    'insert_table_at_placeholder' {
      Insert-HwpTableAtPlaceholder $Hwp ([string]$Operation.placeholder) ([object[]]$Operation.rows)
    }
    default {
      throw "Unsupported operation type: $($Operation.type)"
    }
  }
}

Export-ModuleMember -Function *-Hwp*, New-HwpAutomation, Resolve-AutoHwpPath, Get-HwpDocumentFormat, Invoke-HwpFillOperation


