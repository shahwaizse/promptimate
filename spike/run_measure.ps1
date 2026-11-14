# Usage: run_measure.ps1 -Text <encoder.gguf> -Prompt "..." -Frames 150 -Steps 50 -Seed 42 -Out <dir> [-Chunk 8]
param([string]$Text, [string]$Prompt, [int]$Frames=150, [int]$Steps=50, [int]$Seed=42, [string]$Out, [string]$Chunk="")
$root = 'D:\unity-text-to-anim'
$kb = "$root\third_party\kimodo.cpp\build\release"
$env:PATH = "$kb\bin;$kb;$env:PATH"
$env:KIMODO_BACKEND = 'vulkan'; $env:KIMODO_PROFILE = '1'
if ($Chunk) { $env:KIMODO_TEXT_LAYER_CHUNK = $Chunk } else { Remove-Item Env:KIMODO_TEXT_LAYER_CHUNK -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Force $Out | Out-Null
$pf = Join-Path $Out 'prompt.txt'; [IO.File]::WriteAllText($pf, $Prompt)
$baseline = ((Get-Counter '\GPU Adapter Memory(*)\Dedicated Usage').CounterSamples | Measure-Object CookedValue -Sum).Sum
$sw = [Diagnostics.Stopwatch]::StartNew()
$p = Start-Process "$kb\kmd-generate.exe" -ArgumentList "`"$root\models\models\kimodo-soma-rp-v1.1-f32.gguf`"","`"$Text`"","`"$pf`"",$Frames,$Steps,$Seed,"`"$Out`"" -NoNewWindow -PassThru -RedirectStandardOutput "$Out\stdout.txt" -RedirectStandardError "$Out\stderr.txt"
$peak = 0
while (-not $p.HasExited) {
  try { $v = ((Get-Counter '\GPU Adapter Memory(*)\Dedicated Usage' -ErrorAction Stop).CounterSamples | Measure-Object CookedValue -Sum).Sum; if ($v -gt $peak) { $peak = $v } } catch {}
  Start-Sleep -Milliseconds 200
}
$sw.Stop()
"exit=$($p.ExitCode) wall_s=$([math]::Round($sw.Elapsed.TotalSeconds,2)) peak_vram_delta_MiB=$([math]::Round(($peak-$baseline)/1MB)) baseline_MiB=$([math]::Round($baseline/1MB))"
