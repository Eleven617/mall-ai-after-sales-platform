Set-Location -LiteralPath (Join-Path $PSScriptRoot "..")
$env:PYTHONPATH = (Resolve-Path ".").Path
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
