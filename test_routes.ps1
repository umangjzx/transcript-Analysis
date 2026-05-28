Write-Host "=== Checking all registered routes ==="
try {
    $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/openapi.json' -TimeoutSec 10 -UseBasicParsing
    $json = $r.Content | ConvertFrom-Json
    $paths = $json.paths.PSObject.Properties.Name | Sort-Object
    foreach ($p in $paths) {
        $methods = ($json.paths.$p.PSObject.Properties.Name) -join ','
        Write-Host "$methods  $p"
    }
} catch {
    Write-Host ("ERROR: " + $_.Exception.Message)
}
