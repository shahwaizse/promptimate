<#
.SYNOPSIS
  One-command setup for Promptimate on Windows: engine, Python env, models, and MCP connection instructions.

.EXAMPLE
  .\setup.ps1                      # interactive: asks you to accept the model licenses
  .\setup.ps1 -AcceptLicenses      # non-interactive
  .\setup.ps1 -Quant q8_0          # pick the text-encoder quality (default: chosen from your VRAM)
#>
param(
  [ValidateSet('auto', 'q4_k_m', 'q8_0')] [string]$Quant = 'auto',
  [switch]$AcceptLicenses,
  [switch]$SkipModels,
  [string]$EngineZip = '',
  [string]$EngineUrl = 'https://github.com/shahwaizse/promptimate/releases/download/v0.3.1/kimodo-engine-win64-vulkan.zip'
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
function Step($n, $msg) { Write-Host "`n[$n/6] $msg" -ForegroundColor Cyan }
function Ok($msg) { Write-Host "  OK  $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  !!  $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "  XX  $msg" -ForegroundColor Red; exit 1 }

Write-Host "Promptimate setup  ($Root)" -ForegroundColor White
# Keep downloads/caches inside the install folder (nothing large lands on C: unless you install there).
$env:HF_HOME = Join-Path $Root '.cache\huggingface'
$env:PIP_CACHE_DIR = Join-Path $Root '.cache\pip'

# 1. GPU / Vulkan ---------------------------------------------------------------------------------------------
Step 1 'Checking GPU (Vulkan)'
$vramGB = 0
$gpus = Get-ItemProperty 'HKLM:\SYSTEM\ControlSet001\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0*' -ErrorAction SilentlyContinue |
  Where-Object { $_.'HardwareInformation.qwMemorySize' } |
  ForEach-Object { [pscustomobject]@{ Name = $_.DriverDesc; GB = [math]::Round($_.'HardwareInformation.qwMemorySize' / 1GB) } }
if ($gpus) { $best = $gpus | Sort-Object GB -Descending | Select-Object -First 1; $vramGB = $best.GB; Ok "$($best.Name), $vramGB GB VRAM" }
else { Warn 'Could not read GPU memory; assuming 8 GB' ; $vramGB = 8 }
if (-not (Test-Path "$env:WINDIR\System32\vulkan-1.dll")) { Fail 'No Vulkan runtime found. Update your GPU driver (AMD / NVIDIA / Intel) and re-run.' }
Ok 'Vulkan runtime present'
if ($vramGB -lt 8) { Warn 'Less than 8 GB VRAM: generation may be slow or fail.' }
if ($Quant -eq 'auto') { $Quant = if ($vramGB -ge 14) { 'q8_0' } else { 'q4_k_m' } }
Ok "Text encoder: $Quant"

# 2. Engine (prebuilt kimodo.cpp, Vulkan) ---------------------------------------------------------------------
Step 2 'Installing the generation engine (kimodo.cpp, Vulkan build)'
$engine = Join-Path $Root 'engine'
$info = Join-Path $engine 'BUILD-INFO.txt'
$current = (Test-Path (Join-Path $engine 'kmd-generate.exe')) -and (Test-Path $info) -and
           ((Get-Content $info -Raw) -match 'engine v0\.3\.1')
if ($current) { Ok 'already installed' }
else {
  if (Test-Path (Join-Path $engine 'kmd-generate.exe')) { Write-Host '  updating the engine to v0.3.1 (low-memory mode)' }
  New-Item -ItemType Directory -Force $engine | Out-Null
  $zip = $EngineZip
  if (-not $zip) {
    $zip = Join-Path $env:TEMP 'kimodo-engine-win64-vulkan.zip'
    Write-Host "  downloading $EngineUrl"
    Invoke-WebRequest -Uri $EngineUrl -OutFile $zip -UseBasicParsing
  }
  Expand-Archive -Path $zip -DestinationPath $engine -Force
  Ok "engine -> $engine"
}
if (-not (Test-Path "$env:WINDIR\System32\vcruntime140_1.dll")) {
  Warn 'Microsoft VC++ runtime missing. Install it from https://aka.ms/vs/17/release/vc_redist.x64.exe and re-run.'
}

# 3. Python environment ---------------------------------------------------------------------------------------
Step 3 'Creating Python environment'
$py = $null
foreach ($cand in @('py -3.12', 'py -3.11', 'py -3.10', 'python')) {
  try {
    $exe, $arg = $cand.Split(' ', 2)
    $v = & $exe $arg -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    if ($v -and [version]$v -ge [version]'3.10') { $py = $cand; break }
  } catch {}
}
if (-not $py) { Fail 'Python 3.10+ not found. Install it from https://www.python.org/downloads/ (tick "Add to PATH").' }
$venvPy = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) { $exe, $arg = $py.Split(' ', 2); & $exe $arg -m venv (Join-Path $Root '.venv') }
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -r (Join-Path $Root 'mcp_server\requirements.txt')
if ($LASTEXITCODE -ne 0) { Fail 'pip install failed' }
Ok ".venv ready ($py)"

# 4. Licenses -------------------------------------------------------------------------------------------------
Step 4 'Model licenses'
Write-Host @'
  The models are free downloads from Hugging Face, each under its own license:
   - Kimodo SOMA motion model:  NVIDIA Open Model License
       https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/
   - LLM2Vec text encoder:      Meta Llama 3 Community License (attribution: "Built with Meta Llama 3")
       https://www.llama.com/llama3/license/
'@
if (-not $SkipModels) {
  if (-not $AcceptLicenses) {
    $answer = Read-Host '  Type "yes" to accept both licenses and download (~6 GB)'
    if ($answer -ne 'yes') { Fail 'Licenses not accepted; nothing downloaded. Re-run when ready.' }
  }
  Ok 'accepted'
}

# 5. Models ---------------------------------------------------------------------------------------------------
Step 5 'Downloading models'
if ($SkipModels) { Warn 'skipped (-SkipModels)' }
else {
  & $venvPy (Join-Path $Root 'scripts\download_models.py') --quant $Quant --output (Join-Path $Root 'models')
  if ($LASTEXITCODE -ne 0) { Fail 'model download failed' }
}

# 6. Next steps -----------------------------------------------------------------------------------------------
Step 6 'Done! Next steps'
$server = Join-Path $Root 'mcp_server\server.py'
$pkg = Join-Path $Root 'unity\com.promptimate.unity\package.json'
Write-Host @"

  1) Unity 6: Window > Package Manager > + > Add package from disk... > $pkg

  2) Connect your AI agent (Claude Code shown; any MCP client works):
       claude mcp add kimodo-motion -e KIMODO_TEXT_QUANT=$Quant -e UNITY_PROJECT="C:\path\to\YourUnityProject" -- "$venvPy" "$server"

     Claude Desktop / other clients: add an MCP server with
       command: $venvPy
       args:    $server
       env:     UNITY_PROJECT=C:\path\to\YourUnityProject

  3) Ask: "make a crowd of 20 people waiting for a bus" and the clips appear in Assets/Promptimate/Generated.

"@ -ForegroundColor White
