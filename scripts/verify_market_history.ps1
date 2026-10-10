param([string]$DataRoot='D:\sindhu\data\market_history')
$taskPython=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$env:PYTHONPATH='D:\sindhu\data\qa_packages'
$env:SINDHU_RESEARCH_NODE=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
Push-Location (Split-Path $PSScriptRoot -Parent)
try { & $taskPython -m market_history.verify --root $DataRoot }
finally { Pop-Location }
