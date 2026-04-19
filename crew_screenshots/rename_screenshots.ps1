param(
  [string]$RawDir = "c:\Users\LENOVO\ss\crew_screenshots\raw",
  [string]$FinalDir = "c:\Users\LENOVO\ss\crew_screenshots\final"
)

$ErrorActionPreference = "Stop"

$targetNames = @(
  "screenshot_01_popup.png",
  "screenshot_02_loading.png",
  "screenshot_03_summary.png",
  "screenshot_04_agents.png",
  "screenshot_05_final_report.png"
)

$files = Get-ChildItem -Path $RawDir -File |
  Where-Object { $_.Extension -match "^\.(png|jpg|jpeg|webp)$" } |
  Sort-Object LastWriteTime, Name

if ($files.Count -lt 5) {
  throw "En az 5 görsel gerekiyor. Bulunan: $($files.Count). Raw klasörü: $RawDir"
}

if (!(Test-Path $FinalDir)) {
  New-Item -ItemType Directory -Force -Path $FinalDir | Out-Null
}

for ($i = 0; $i -lt 5; $i++) {
  $src = $files[$i].FullName
  $dst = Join-Path $FinalDir $targetNames[$i]
  Copy-Item -LiteralPath $src -Destination $dst -Force
}

Write-Output "Tamamlandi. Dosyalar:"
$targetNames | ForEach-Object { Write-Output (Join-Path $FinalDir $_) }
