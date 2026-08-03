# API key comes from the environment — never hardcode it here. This repo is
# public, so a literal key in this file is a published credential.
#   PowerShell:  $env:API_KEY = "<key>"; .\run_examples.ps1
if (-not $env:API_KEY) {
    Write-Host "API_KEY is not set. Set it before running:" -ForegroundColor Red
    Write-Host '  $env:API_KEY = "<your-key>"' -ForegroundColor Yellow
    exit 1
}
$apiKey = $env:API_KEY

$baseUrl = "https://audio-safety-backend-781782361175.us-central1.run.app/analyze/transcript"
$statusUrl = "https://audio-safety-backend-781782361175.us-central1.run.app/report"
$headers = @{ "Content-Type" = "application/json"; "X-API-Key" = $apiKey }
$statusHeaders = @{ "X-API-Key" = $apiKey }

# Get all .txt example files
$files = Get-ChildItem "examples\*.txt" | Sort-Object Name
Write-Host "Found $($files.Count) transcript files to submit" -ForegroundColor Cyan
Write-Host ""

$startTime = Get-Date
$submissions = @()

# Submit all files (with delay to avoid rate limit)
foreach ($file in $files) {
    $transcript = Get-Content $file.FullName -Raw -Encoding UTF8
    if (-not $transcript -or $transcript.Length -lt 10) {
        Write-Host "  SKIP - $($file.Name): empty or too short" -ForegroundColor Yellow
        continue
    }
    $body = '{"filename": "' + $file.Name.Replace('"','\"') + '", "transcript": ' + ($transcript | ConvertTo-Json) + '}'
    try {
        $r = Invoke-RestMethod -Uri $baseUrl -Method POST -Headers $headers -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) -ContentType "application/json; charset=utf-8"
        $submissions += @{ id = $r.id; filename = $file.Name; submitted = Get-Date }
        Write-Host "  Submitted #$($r.id) - $($file.Name)" -ForegroundColor Green
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        Write-Host "  FAILED ($code) - $($file.Name): $($_.Exception.Message)" -ForegroundColor Red
    }
    # 2 second delay between submissions (rate limit is now 60/min)
    Start-Sleep -Seconds 2
}

$submitEnd = Get-Date
Write-Host ""
Write-Host "All $($submissions.Count) files submitted in $([math]::Round(($submitEnd - $startTime).TotalSeconds))s" -ForegroundColor Cyan
Write-Host "Waiting for all to complete..." -ForegroundColor Yellow

# Poll until all complete (max 15 min)
$timeout = (Get-Date).AddMinutes(15)
$completed = @{}

while ($completed.Count -lt $submissions.Count -and (Get-Date) -lt $timeout) {
    Start-Sleep -Seconds 15
    foreach ($sub in $submissions) {
        if ($completed.ContainsKey($sub.id)) { continue }
        try {
            $s = Invoke-RestMethod -Uri "$statusUrl/$($sub.id)/status" -Method GET -Headers $statusHeaders
            if ($s.status -ne "PROCESSING") {
                $completed[$sub.id] = @{ status = $s.status; time = Get-Date }
                Write-Host "  #$($sub.id) $($sub.filename): $($s.status)" -ForegroundColor $(if($s.status -eq "COMPLETED"){"Green"}else{"Red"})
            }
        } catch {}
    }
    $pending = $submissions.Count - $completed.Count
    if ($pending -gt 0) {
        Write-Host "  ... $pending still processing" -ForegroundColor DarkGray
    }
}

$endTime = Get-Date
$totalSeconds = [math]::Round(($endTime - $startTime).TotalSeconds)

Write-Host ""
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "  RESULTS" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "  Total files: $($submissions.Count)"
Write-Host "  Completed: $($completed.Count)"
Write-Host "  Failed: $(($completed.Values | Where-Object { $_.status -ne 'COMPLETED' }).Count)"
Write-Host "  Total time: ${totalSeconds}s ($([math]::Round($totalSeconds/60, 1)) min)"
Write-Host "  Avg per file: $([math]::Round($totalSeconds / [math]::Max(1,$submissions.Count)))s"
Write-Host "=" * 60 -ForegroundColor Cyan
