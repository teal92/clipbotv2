$env:CLIPBOT_ORIGIN='http://127.0.0.1:8766'
$env:CLIPBOT_LOCAL_SIGNUP='1'
$env:CLIPBOT_DEV_BYPASS='1'
& (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') -m uvicorn server.app:create_app --factory --app-dir $PSScriptRoot --host 127.0.0.1 --port 8766 --no-proxy-headers --no-access-log
