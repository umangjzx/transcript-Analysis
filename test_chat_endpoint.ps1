$body = @{
    report_id = 1
    question  = 'What are the main risk factors?'
} | ConvertTo-Json

Write-Host "=== Testing POST /chat (no auth, root endpoint) ==="
try {
    $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/chat' `
        -Method POST -ContentType 'application/json' `
        -Body $body -TimeoutSec 120 -UseBasicParsing
    Write-Host ("STATUS: " + $r.StatusCode)
    Write-Host $r.Content
} catch {
    Write-Host ("ERROR: " + $_.Exception.Message)
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        Write-Host $reader.ReadToEnd()
    }
}

Write-Host ""
Write-Host "=== Testing POST /api/v1/chat (v1 router, needs auth) ==="
try {
    $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/v1/chat' `
        -Method POST -ContentType 'application/json' `
        -Body $body -TimeoutSec 120 -UseBasicParsing
    Write-Host ("STATUS: " + $r.StatusCode)
    Write-Host $r.Content
} catch {
    Write-Host ("ERROR: " + $_.Exception.Message)
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        Write-Host $reader.ReadToEnd()
    }
}
