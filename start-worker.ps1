$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$workerPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $workerPython)) { throw 'ClipBot local environment is missing. Follow LIVE-PIPELINE-TEST.md first.' }
& $workerPython -m worker.local_app --service https://clipbot.your-domain.example
