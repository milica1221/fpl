# FPL Cache Strategy

## Cache Timeouts

| Data Type | Cache Duration | Reasoning |
|-----------|----------------|-----------|
| Bootstrap Data | 1 hour | Player info, teams, positions rarely change |
| Current Event Info | 30 minutes | Gameweek status updates moderately |
| Player Names | 1 hour | Player names rarely change mid-season |
| League Standings | 10 minutes | Moderate updates during active gameweeks |
| Live Points (Active GW) | 5 minutes | High frequency updates during live games |
| Live Points (Finished GW) | 2 hours | No changes after gameweek ends |
| Fixtures | 10 minutes | Fixture status updates moderately |
| Historical Data | 30 minutes | Historical scores don't change often |

## Cache Strategy by Endpoint

### High Frequency (Live Data)
- **Live Points**: 5 minutes during active gameweek, 2 hours for finished
- **Players to Play**: No cache (always fresh for accuracy)
- **Current Team Picks**: No cache (user-specific, changes frequently)

### Medium Frequency 
- **League Standings**: 10 minutes
- **Fixtures Status**: 10 minutes
- **Historical Scores**: 30 minutes

### Low Frequency (Static Data)
- **Bootstrap/Player Data**: 1 hour
- **Player Names**: 1 hour
- **Current Event Info**: 30 minutes

## Cache Invalidation

### Automatic
- Time-based expiration for all cached data
- Dynamic timeout based on gameweek status

### Manual
- `/admin/clear-cache` - Clear live data cache
- `/admin/cache-stats` - View cache performance

## Performance Benefits

1. **Reduced API Calls**: ~80% reduction in FPL API requests
2. **Faster Response Times**: Cached data served in <10ms vs 200-500ms API calls
3. **Better User Experience**: Faster page loads, especially during peak times
4. **API Rate Limit Protection**: Reduces risk of hitting FPL API limits

## Monitoring

- Cache hit/miss ratios available at `/admin/cache-stats`
- Redis memory usage tracking
- Automatic cache warming for frequently accessed data
