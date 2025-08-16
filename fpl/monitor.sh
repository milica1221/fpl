#!/bin/bash

# FPL Application Resource Monitor
# Use this to monitor resource usage on your droplet

echo "=== FPL Application Resource Monitor ==="
echo "Date: $(date)"
echo ""

echo "=== System Resources ==="
echo "Memory Usage:"
free -h

echo ""
echo "CPU Usage:"
top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print "CPU Usage: " 100 - $1 "%"}'

echo ""
echo "Disk Usage:"
df -h /

echo ""
echo "=== Docker Container Status ==="
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}"

echo ""
echo "=== Redis Memory Usage ==="
docker exec mel-fpl-redis redis-cli INFO memory | grep -E "(used_memory_human|used_memory_peak_human|maxmemory_human)"

echo ""
echo "=== Redis Cache Statistics ==="
docker exec mel-fpl-redis redis-cli INFO stats | grep -E "(keyspace_hits|keyspace_misses|evicted_keys)"

echo ""
echo "=== Network Connections ==="
ss -tuln | grep :5000
ss -tuln | grep :6379

echo ""
echo "=== Application Logs (last 10 lines) ==="
docker logs mel-fpl --tail 10

echo ""
echo "=== Redis Cache Keys Count ==="
docker exec mel-fpl-redis redis-cli DBSIZE
