$runtimeRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$apiListener = Get-NetTCPConnection -State Listen -LocalPort 8000 | Select-Object -First 1
$apiCommand = Get-CimInstance Win32_Process -Filter "ProcessId=$($apiListener.OwningProcess)"
if ($apiCommand.CommandLine -notmatch 'uvicorn app.main:app') { throw 'API process identity did not match' }
Stop-Process -Id $apiListener.OwningProcess
$env:PYTHONPATH = Join-Path $runtimeRoot 'apps/api'
$apiProcess = Start-Process -FilePath (Join-Path $runtimeRoot '.venv/Scripts/python.exe') -ArgumentList '-m','uvicorn','app.main:app','--env-file','.env.local','--host','127.0.0.1','--port','8000','--no-access-log' -WorkingDirectory $runtimeRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'api.out.log') -RedirectStandardError (Join-Path $PSScriptRoot 'api.err.log') -PassThru
"Restarted API launcher: $($apiProcess.Id)"
