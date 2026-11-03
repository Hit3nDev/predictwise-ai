# Starts PredictWise on this computer: backend on :8000, website on :5173, then opens the browser.
# Put your Groq key in backend\.env first; without it the open-ended chat is off (everything else works).
$root = $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "No .venv found. First run:  python -m venv .venv ; .venv\Scripts\pip install -r backend\requirements.txt"
    exit 1
}
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$root\backend'; & '$python' -m uvicorn main:app --port 8000"
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$root\frontend'; npm run dev"
Start-Sleep -Seconds 6
Start-Process "http://localhost:5173"
