# FPL Application Resource Monitor - Windows PowerShell Version
# Use this to monitor resource usage

Write-Host "=== FPL Application Resource Monitor ===" -ForegroundColor Green
Write-Host "Date: $(Get-Date)" -ForegroundColor Yellow
Write-Host ""

Write-Host "=== Docker Container Status ===" -ForegroundColor Green
docker stats --no-stream --format "table {{.Container}}`t{{.CPUPerc}}`t{{.MemUsage}}`t{{.NetIO}}`t{{.BlockIO}}"

Write-Host ""
Write-Host "=== Redis Memory Usage ===" -ForegroundColor Green
docker exec mel-fpl-redis redis-cli INFO memory | Select-String -Pattern "(used_memory_human|used_memory_peak_human|maxmemory_human)"

Write-Host ""
Write-Host "=== Redis Cache Statistics ===" -ForegroundColor Green
docker exec mel-fpl-redis redis-cli INFO stats | Select-String -Pattern "(keyspace_hits|keyspace_misses|evicted_keys)"

Write-Host ""
Write-Host "=== Application Logs (last 10 lines) ===" -ForegroundColor Green
docker logs mel-fpl --tail 10

Write-Host ""
Write-Host "=== Redis Cache Keys Count ===" -ForegroundColor Green
$keyCount = docker exec mel-fpl-redis redis-cli DBSIZE
Write-Host "Total cache keys: $keyCount" -ForegroundColor Cyan

Write-Host ""
Write-Host "=== Container Health ===" -ForegroundColor Green
docker ps --filter "name=mel-fpl" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
