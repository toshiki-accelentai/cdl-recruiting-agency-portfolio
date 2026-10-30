# B3: deploy the API + worker (retry, logging, X-API-Key) to hermes-vps. Run from the repo root in PowerShell 5.1:
#   powershell -ExecutionPolicy Bypass -File scripts\deploy_api_to_vps.ps1
# Safe to read first. It never prints a secret. Stops at the first failing step.
$ErrorActionPreference = "Stop"
# Set once per machine, never committed: CDL_DEPLOY_KEY = full path of the ssh key, CDL_DEPLOY_REMOTE = user@server-ip
$key    = $env:CDL_DEPLOY_KEY
$remote = $env:CDL_DEPLOY_REMOTE
if (-not $key -or -not $remote) { throw "set CDL_DEPLOY_KEY and CDL_DEPLOY_REMOTE first" }
$dir    = "/opt/cdl-api"
$stamp  = Get-Date -Format "yyyyMMdd-HHmmss"
$tmp    = Join-Path $env:TEMP "cdl-api-src-$stamp.tar"

function Run-Remote([string]$cmd) {
    ssh -i $key -o ConnectTimeout=15 $remote $cmd
    if ($LASTEXITCODE -ne 0) { throw "remote command failed: $cmd" }
}

foreach ($f in @("api\deploy\.env.api", "api\deploy\compose.yaml", "api\app\db.py")) {
    if (-not (Test-Path $f)) { throw "missing local file: $f" }
}

Write-Host "1/6 backup on the server (rollback copies: compose.yaml.before-$stamp, src.before-$stamp)"
Run-Remote "cd $dir && cp compose.yaml compose.yaml.before-$stamp && cp -a src src.before-$stamp"

Write-Host "2/6 copy the API key file (chmod 600)"
scp -i $key api\deploy\.env.api "${remote}:${dir}/.env.api"
if ($LASTEXITCODE -ne 0) { throw "scp .env.api failed" }
Run-Remote "chmod 600 $dir/.env.api"

Write-Host "3/6 copy the source code"
tar -C api --exclude=__pycache__ -cf $tmp app migrations requirements.txt Dockerfile .dockerignore
if ($LASTEXITCODE -ne 0) { throw "tar failed" }
scp -i $key $tmp "${remote}:/tmp/cdl-api-src.tar"
if ($LASTEXITCODE -ne 0) { throw "scp source failed" }
Remove-Item $tmp
Run-Remote "rm -rf $dir/src/app && tar -C $dir/src -xf /tmp/cdl-api-src.tar && rm /tmp/cdl-api-src.tar"

Write-Host "4/6 copy compose.yaml"
scp -i $key api\deploy\compose.yaml "${remote}:${dir}/compose.yaml"
if ($LASTEXITCODE -ne 0) { throw "scp compose failed" }

Write-Host "5/6 rebuild and restart both containers"
Run-Remote "cd $dir && sudo -n docker compose up -d --build 2>&1 | tail -15"
Start-Sleep -Seconds 25

Write-Host "6/6 checks"
Run-Remote "cd $dir && sudo -n docker compose ps --format '{{.Name}} {{.Status}}'"
# cmd.exe pipes the raw bytes. PowerShell 5.1 would put a BOM in front of the script, and python rejects it.
$checkCmd = "ssh -i `"$key`" $remote `"sudo -n docker exec -i cdl-api-cdl-api-1 python -`""
cmd /c "type scripts\check_api_key_on_server.py | $checkCmd"
Run-Remote "cd $dir && sudo -n docker compose logs --tail 6 cdl-api worker 2>&1 | cut -c1-200"
Write-Host "Done. Rollback if needed: copy compose.yaml.before-$stamp back and src.before-$stamp to src, then docker compose up -d --build."
