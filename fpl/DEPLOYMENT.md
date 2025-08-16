# FPL Application Deployment Guide

## Server Specifications
- **Recommended**: 2GB RAM / 2 vCPUs DigitalOcean Droplet (Basic tier)
- **Minimum**: 1GB RAM / 1 vCPU (može raditi ali sa ograničenjima)

## Resource Allocation
- **Redis**: 512MB maksimalno (25% RAM-a)
- **Flask aplikacija**: ~300-500MB 
- **System + Docker**: ~500-700MB
- **Rezerva**: ~300-500MB

## Redis Optimizacija
Aplikacija je konfigurisana sa:
- `maxmemory 512mb` - ograničava Redis na 512MB
- `maxmemory-policy allkeys-lru` - briše najstarije ključeve kada se popuni
- Automatsko čišćenje cache-a svaki minut
- Optimizovani timeout-i za različite tipove podataka

## Cache Strategija
```
Bootstrap data: 2h (retko se menja)
Player names: 2h (retko se menja) 
League standings: 1h (umereno često)
Live points: 5min (često tokom mečeva)
Historical data: 2h (statični podaci)
Fixtures: 1h (umereno često)
```

## Deployment na DigitalOcean

1. **Kreiraj droplet:**
   ```bash
   # Ubuntu 22.04 LTS
   # 2GB RAM / 2 vCPUs
   # Dodaj SSH ključ
   ```

2. **Instaliraj Docker:**
   ```bash
   sudo apt update
   sudo apt install docker.io docker-compose -y
   sudo systemctl enable docker
   sudo usermod -aG docker $USER
   ```

3. **Deploy aplikaciju:**
   ```bash
   git clone https://github.com/your-repo/fpl.git
   cd fpl/fpl
   docker compose up -d
   ```

4. **Setup nginx (opciono):**
   ```bash
   sudo apt install nginx
   # Konfiguriši reverse proxy za port 5000
   ```

## Monitoring

Koristi `monitor.ps1` (Windows) ili `monitor.sh` (Linux):
```powershell
./monitor.ps1
```

Ključne metriki:
- **Redis memorija**: treba biti < 512MB
- **Aplikacija memorija**: treba biti < 500MB  
- **Cache hit rate**: treba biti > 80%
- **Response time**: treba biti < 2s

## Performance Tips

1. **Redis optimizacija je već uključena**
2. **Cache strategija je optimizovana za FPL API**
3. **Fast mode** za brže učitavanje
4. **Batch requests** za league data

## Troubleshooting

Ako aplikacija konzumira previše memorije:
```bash
# Restartuj Redis cache
docker restart mel-fpl-redis

# Očisti cache ručno
docker exec mel-fpl-redis redis-cli FLUSHALL

# Prověri memory usage
docker stats
```

## Costs na DigitalOcean
- **Basic 2GB droplet**: $12/mesec
- **1GB droplet**: $6/mesec (može raditi ali sa ograničenjima)

## Autoscaling (opciono)
Možete podesiti aplikaciju da se skalira na osnovu load-a:
- Povećaj cache timeout-e tokom visokog saobraćaja
- Koristi Redis Cluster za veće scale
- Dodaj load balancer za multiple instance
