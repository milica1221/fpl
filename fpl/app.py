from flask import Flask, render_template, request, jsonify
from flask_caching import Cache
import requests
import statistics
import os
import json
import time
import redis

app = Flask(__name__)

# Cache configuration
cache_config = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_REDIS_URL": os.environ.get('REDIS_URL', 'redis://localhost:6379/0'),
    "CACHE_DEFAULT_TIMEOUT": 300  # 5 minutes default timeout
}

app.config.from_mapping(cache_config)
cache = Cache(app)

# Cache timeout constants (in seconds) - optimized for performance
CACHE_TIMEOUT_BOOTSTRAP = 7200  # 2 hours - bootstrap data changes rarely
CACHE_TIMEOUT_CURRENT_EVENT = 3600  # 1 hour - gameweek info changes rarely during week
CACHE_TIMEOUT_LEAGUE_STANDINGS = 3600  # 1 hour - league standings (increased from 30 minutes)
CACHE_TIMEOUT_PLAYER_NAMES = 7200  # 2 hours - player names rarely change
CACHE_TIMEOUT_LIVE_POINTS = 300  # 5 minutes - live points during active gameweek (increased from 3 minutes)
CACHE_TIMEOUT_HISTORICAL = 7200  # 2 hours - historical data is static except current week (increased from 1 hour)
CACHE_TIMEOUT_FIXTURES = 3600  # 1 hour - fixtures data (increased from 30 minutes)

# Cache helper functions
@cache.memoize(timeout=CACHE_TIMEOUT_FIXTURES)
def get_fixtures_for_event(event_number):
    """Get fixtures for specific event - cached for 30 minutes"""
    fixtures_url = f"https://fantasy.premierleague.com/api/fixtures/?event={event_number:02d}"
    data = optimized_api_request(fixtures_url)
    return data if data is not None else []

@cache.memoize(timeout=CACHE_TIMEOUT_BOOTSTRAP)
def get_bootstrap_data():
    """Get bootstrap static data - cached for 2 hours"""
    data = optimized_api_request("https://fantasy.premierleague.com/api/bootstrap-static/")
    return data if data is not None else {}

# Cache management functions
def clear_live_cache():
    """Clear cache for live data during active gameweeks"""
    current_event = get_current_event()
    cache.delete(f"live_points_{current_event}")
    print(f"Cleared live cache for event {current_event}")

def clear_all_cache():
    """Clear all cache - use sparingly"""
    cache.clear()
    print("Cleared all cache")

def optimized_api_request(url, max_retries=2, timeout=10):
    """Optimized API request with retry logic and timeout"""
    for attempt in range(max_retries + 1):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            if attempt < max_retries:
                print(f"Timeout on attempt {attempt + 1}, retrying...")
                time.sleep(0.5)  # Short delay before retry
                continue
            else:
                print(f"API request timeout after {max_retries + 1} attempts: {url}")
                return None
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                print(f"API error on attempt {attempt + 1}: {e}, retrying...")
                time.sleep(0.5)
                continue
            else:
                print(f"API request failed after {max_retries + 1} attempts: {url}, error: {e}")
                return None
    return None

@app.route('/admin/clear-cache')
def admin_clear_cache():
    """Admin endpoint to clear cache"""
    clear_live_cache()
    return {"status": "Cache cleared", "timestamp": time.time()}

@app.route('/admin/cache-stats')
def admin_cache_stats():
    """Admin endpoint to view cache statistics"""
    try:
        # Get Redis info if using Redis cache
        r = redis.from_url(os.environ.get('REDIS_URL', 'redis://localhost:6379/0'))
        info = r.info()
        return {
            "cache_type": "Redis",
            "redis_info": {
                "used_memory": info.get('used_memory_human'),
                "connected_clients": info.get('connected_clients'),
                "total_commands_processed": info.get('total_commands_processed'),
                "keyspace_hits": info.get('keyspace_hits'),
                "keyspace_misses": info.get('keyspace_misses')
            }
        }
    except Exception as e:
        return {"error": str(e), "cache_type": "Unknown"}

# Player names mapping
PLAYER_NAMES = {
    4909598: "grmilica",
    4658819: "Hell Patrol", 
    3070732: "NEPOBEDIVI",
    2227937: "Sport bar 22",
    4895434: "ValjevoJeSvetoMesto",
    729967: "mixXx007"
}

# League ID for Nosata liga
LEAGUE_ID = 412037

@cache.memoize(timeout=CACHE_TIMEOUT_CURRENT_EVENT)
def get_current_event():
    """Get the current gameweek number from FPL API - cached for 30 minutes"""
    try:
        response = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/")
        response.raise_for_status()
        data = response.json()
        
        # Find current event
        for event in data["events"]:
            if event["is_current"]:
                return event["id"]
        
        # If no current event, return 1
        return 1
    except Exception as e:
        print(f"Error getting current event: {e}")
        return 1

@cache.memoize(timeout=CACHE_TIMEOUT_CURRENT_EVENT)
def get_gameweek_status():
    """Get current gameweek status - cached for 30 minutes"""
    try:
        response = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/")
        response.raise_for_status()
        data = response.json()
        
        current_event_id = None
        current_event_data = None
        
        # Find current event
        for event in data["events"]:
            if event["is_current"]:
                current_event_id = event["id"]
                current_event_data = event
                break
        
        if not current_event_data:
            return {"event_id": 1, "status": "not_started", "display_event": 1}
        
        # Check if gameweek is live (started but not finished)
        if current_event_data["finished"]:
            # Current GW is finished, use it for display
            return {"event_id": current_event_id, "status": "finished", "display_event": current_event_id}
        elif current_event_data["is_current"]:
            # Current GW is live
            return {"event_id": current_event_id, "status": "live", "display_event": current_event_id}
        else:
            # Find the last finished gameweek
            last_finished_event = 1
            for event in data["events"]:
                if event["finished"]:
                    last_finished_event = event["id"]
            
            return {"event_id": current_event_id, "status": "not_started", "display_event": last_finished_event}
        
    except Exception as e:
        print(f"Error getting gameweek status: {e}")
        return {"event_id": 1, "status": "not_started", "display_event": 1}

@cache.memoize(timeout=CACHE_TIMEOUT_PLAYER_NAMES)
def get_player_names():
    """Get all player names from FPL API - cached for 1 hour"""
    try:
        response = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/")
        response.raise_for_status()
        data = response.json()
        
        # Create a mapping of element_id -> player_name
        player_names = {}
        for element in data["elements"]:
            full_name = f"{element['first_name']} {element['second_name']}"
            # Use web_name if it's shorter and more recognizable
            if len(element['web_name']) < len(full_name) and element['web_name']:
                player_names[element['id']] = element['web_name']
            else:
                player_names[element['id']] = full_name
        
        return player_names
    except Exception as e:
        print(f"Error getting player names: {e}")
        return {}

@cache.memoize(timeout=CACHE_TIMEOUT_LEAGUE_STANDINGS)
def get_league_standings(league_id):
    """Get league standings from FPL API - cached for 10 minutes"""
    try:
        response = requests.get(f"https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/")
        response.raise_for_status()
        data = response.json()
        
        # Extract all entries from the league
        league_entries = []
        if "standings" in data and "results" in data["standings"]:
            for entry in data["standings"]["results"]:
                league_entries.append({
                    "entry_id": entry["entry"],
                    "entry_name": entry["entry_name"],
                    "player_name": entry["player_name"],
                    "total": entry["total"]
                })
        
        return {
            "league_name": data.get("league", {}).get("name", "League"),
            "entries": league_entries
        }
    except Exception as e:
        print(f"Error getting league standings: {e}")
        return {"league_name": "League", "entries": []}

def get_players_to_play(entry_id, current_event, player_names):
    """Get list of players yet to play for a specific team with current playing status"""
    try:
        # Get current week team picks
        picks_url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/event/{current_event:02d}/picks/"
        response = requests.get(picks_url)
        response.raise_for_status()
        picks_data = response.json()
        
        # Get fixtures for current event (cached)
        fixtures_data = get_fixtures_for_event(current_event)
        
        # Get bootstrap data (cached)
        bootstrap_data = get_bootstrap_data()
        
        # Create player to team mapping
        player_to_team = {}
        for element in bootstrap_data.get("elements", []):
            player_to_team[element["id"]] = element["team"]
        
        # Create team to fixture status mapping
        team_status = {}  # team_id -> 'finished', 'live', 'not_started'
        for fixture in fixtures_data:
            team_h = fixture["team_h"]
            team_a = fixture["team_a"]
            
            if fixture.get("finished", False):
                status = "finished"
            elif fixture.get("started", False):
                status = "live"  # Game is currently playing
            else:
                status = "not_started"  # Game hasn't started yet
            
            team_status[team_h] = status
            team_status[team_a] = status
        
        # Find players yet to play (not finished) and categorize them
        players_to_play = []
        currently_playing = []
        
        for pick in picks_data["picks"]:
            if pick["multiplier"] > 0:  # Only starting XI
                element_id = pick["element"]
                player_team = player_to_team.get(element_id)
                team_match_status = team_status.get(player_team, "not_started")
                
                # If player's team hasn't finished their game yet
                if team_match_status != "finished":
                    player_name = player_names.get(element_id, f"Player {element_id}")
                    is_captain = pick["is_captain"]
                    is_vice_captain = pick["is_vice_captain"]
                    is_triple_captain = pick.get("is_triple_captain", False)
                    
                    player_info = {
                        "name": player_name,
                        "is_captain": is_captain,
                        "is_vice_captain": is_vice_captain,
                        "is_triple_captain": is_triple_captain,
                        "multiplier": pick["multiplier"],
                        "status": team_match_status  # 'live' or 'not_started'
                    }
                    
                    if team_match_status == "live":
                        currently_playing.append(player_info)
                    else:
                        players_to_play.append(player_info)
        
        # Return both lists - this will help with UI logic
        return {
            "waiting": players_to_play,  # Players waiting for their game to start
            "playing": currently_playing,  # Players currently playing
            "total": players_to_play + currently_playing  # All non-finished players
        }
    except Exception as e:
        print(f"Error getting players to play for entry {entry_id}: {e}")
        return {
            "waiting": [],
            "playing": [],
            "total": []
        }

def get_captain_info(entry_id, current_event, player_names):
    """Get captain information for a specific team"""
    try:
        # Get current week team picks
        picks_url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/event/{current_event:02d}/picks/"
        response = requests.get(picks_url)
        response.raise_for_status()
        picks_data = response.json()
        
        # Get live points data
        live_url = f"https://fantasy.premierleague.com/api/event/{current_event:02d}/live/"
        live_response = requests.get(live_url)
        live_response.raise_for_status()
        live_data = live_response.json()
        
        # Get fixtures for current event (cached)
        fixtures_data = get_fixtures_for_event(current_event)
        
        # Get bootstrap data (cached)
        bootstrap_data = get_bootstrap_data()
        
        # Create player to team mapping
        player_to_team = {}
        for element in bootstrap_data.get("elements", []):
            player_to_team[element["id"]] = element["team"]
        
        # Create team to fixture mapping (which games are finished/playing)
        finished_teams = set()
        playing_teams = set()
        for fixture in fixtures_data:
            if fixture.get("finished", False):
                finished_teams.add(fixture["team_h"])
                finished_teams.add(fixture["team_a"])
            elif fixture.get("started", False) and not fixture.get("finished", False):
                playing_teams.add(fixture["team_h"])
                playing_teams.add(fixture["team_a"])
        
        # Find captain
        captain_element_id = None
        for pick in picks_data["picks"]:
            if pick["is_captain"]:
                captain_element_id = pick["element"]
                break
        
        if captain_element_id:
            captain_name = player_names.get(captain_element_id, f"Player {captain_element_id}")
            captain_team = player_to_team.get(captain_element_id)
            
            # Get captain's points from live data
            captain_points = 0
            for element in live_data.get("elements", []):
                if element["id"] == captain_element_id:
                    captain_points = element["stats"]["total_points"] * 2  # Captain gets double points
                    break
            
            # Determine captain status
            if captain_team and captain_team in finished_teams:
                return {
                    "name": captain_name,
                    "points": captain_points,
                    "played": True,
                    "is_playing": False
                }
            elif captain_team and captain_team in playing_teams:
                return {
                    "name": captain_name,
                    "points": captain_points,
                    "played": False,
                    "is_playing": True
                }
            else:
                return {
                    "name": captain_name,
                    "points": 0,
                    "played": False,
                    "is_playing": False
                }
        
        return None
    except Exception as e:
        print(f"Error getting captain info for entry {entry_id}: {e}")
        return None

@app.route('/')
def index():
    # Always use full mode with better caching
    fast_mode = False
    
    team1_entry_ids = [4909598, 4658819, 3070732]
    team2_entry_ids = [2227937, 4895434, 729967]

    # Get current gameweek and its status
    gw_status = get_gameweek_status()
    current_event = gw_status["event_id"]
    display_event = gw_status["display_event"]  # This is what Detalji tab will show
    gw_status_text = gw_status["status"]

    # Get player names ONCE and cache them
    player_names = get_player_names()

    if fast_mode:
        # Fast mode - get basic cached data only, skip heavy live calculations
        team1_scores = fetch_historical_data(team1_entry_ids, current_event - 1, player_names)
        team2_scores = fetch_historical_data(team2_entry_ids, current_event - 1, player_names)
        
        # Calculate basic statistics
        team1_total = sum(sum(player['total_scores_by_week'].values()) for player in team1_scores)
        team2_total = sum(sum(player['total_scores_by_week'].values()) for player in team2_scores)
        
        # Calculate win statistics (simplified)
        team1_wins = 0
        team2_wins = 0
        for week in range(1, current_event):
            team1_week_total = sum(player['total_scores_by_week'].get(week, 0) for player in team1_scores)
            team2_week_total = sum(player['total_scores_by_week'].get(week, 0) for player in team2_scores)
            if team1_week_total > team2_week_total:
                team1_wins += 1
            elif team2_week_total > team1_week_total:
                team2_wins += 1

        # Get basic league data from cache
        league_data = get_league_standings(LEAGUE_ID)
        league_entries = league_data["entries"] if league_data else []
        league_name = league_data["league_name"] if league_data else "Nosata liga"
        
        # Add missing attributes for fast mode compatibility
        league_live_data = []
        for entry in league_entries[:20]:
            league_live_data.append({
                "entry_id": entry["entry_id"],
                "entry_name": entry["entry_name"],
                "player_name": entry["player_name"],
                "total_season_points": entry.get("total", 0),
                "live_points": 0,  # No live data in fast mode
                "players_to_play": [],  # Empty in fast mode
                "players_to_play_count": 0,  # No players to play data in fast mode
                "captain_info": None  # No captain info in fast mode
            })
        
        return render_template('index.html', 
                           team1_scores=team1_scores, 
                           team2_scores=team2_scores, 
                           team1_sums={"total": team1_total},
                           team2_sums={"total": team2_total}, 
                           team1_wins=team1_wins, 
                           team2_wins=team2_wins,
                           team1_points=team1_total, 
                           team2_points=team2_total,
                           analytics=None,
                           has_current_data=len(team1_scores) > 0 and len(team2_scores) > 0,
                           team1_live=[],
                           team2_live=[],
                           current_event=current_event,
                           team1_analytics=[],
                           team2_analytics=[],
                           display_event=display_event,
                           gw_status=gw_status_text,
                           league_name=league_name,
                           league_live_data=league_live_data,
                           colored_teams=["Sport bar 22", "NEPOBEDIVI", "Hell Patrol", "ValjevoJeSvetoMesto", "grmilica", "mixXx007"],
                           fast_mode=True)

    # Normal mode - full data loading (currently not used for performance)
    # Fetch league standings for Nosata liga tab
    league_data = get_league_standings(LEAGUE_ID)
    league_entries = league_data["entries"]
    league_name = league_data["league_name"]
    
    # Fetch fresh historical data for all league entries (including live data for current gameweek)
    league_live_data = []
    if league_entries:
        league_entry_ids = [entry["entry_id"] for entry in league_entries]
        
        # Get fresh historical data with live current gameweek for all league players
        league_fresh_data = fetch_historical_data(league_entry_ids, current_event, player_names)
        
        # Get actual live points for all league players for current gameweek
        league_live_points = fetch_live_data_optimized(league_entry_ids, current_event, player_names)
        
        # Combine league standings with fresh data
        for i, entry in enumerate(league_entries):
            entry_id = entry["entry_id"]
            # Find corresponding fresh historical data
            fresh_data = next((data for data in league_fresh_data if data["entry_id"] == entry_id), None)
            
            # Find corresponding live data for current gameweek
            live_data = next((data for data in league_live_points if data["entry_id"] == entry_id), None)
            
            # Get players yet to play for this team
            players_data = get_players_to_play(entry_id, current_event, player_names)
            
            # Get captain information for this team
            captain_info = get_captain_info(entry_id, current_event, player_names)
            
            if fresh_data:
                # Calculate total season points using fresh data (including live current gameweek)
                fresh_total_points = sum(fresh_data["total_scores_by_week"].values())
                
                # Get actual live points for current gameweek
                live_points_for_gw = live_data["total_points"] if live_data else 0
                
                league_live_data.append({
                    "entry_id": entry_id,
                    "entry_name": entry["entry_name"],
                    "player_name": entry["player_name"],
                    "total_season_points": fresh_total_points,  # Use fresh total
                    "live_points": live_points_for_gw,  # Use actual live points
                    "players_to_play": players_data["total"],  # All non-finished players
                    "players_waiting": players_data["waiting"],  # Players waiting
                    "players_playing": players_data["playing"],  # Players currently playing
                    "players_to_play_count": len(players_data["total"]),
                    "has_live_players": len(players_data["playing"]) > 0,  # Has players currently playing
                    "captain_info": captain_info
                })
            else:
                # Fallback to old data if fresh data not available
                live_points_for_gw = live_data["total_points"] if live_data else 0
                
                league_live_data.append({
                    "entry_id": entry_id,
                    "entry_name": entry["entry_name"],
                    "player_name": entry["player_name"],
                    "total_season_points": entry["total"],
                    "live_points": live_points_for_gw,  # Use actual live points even in fallback
                    "players_to_play": players_data["total"],  # All non-finished players
                    "players_waiting": players_data["waiting"],  # Players waiting
                    "players_playing": players_data["playing"],  # Players currently playing
                    "players_to_play_count": len(players_data["total"]),
                    "has_live_players": len(players_data["playing"]) > 0,  # Has players currently playing
                    "captain_info": captain_info
                })
    
    # Sort league data by fresh total season points
    league_live_data.sort(key=lambda x: x["total_season_points"], reverse=True)

    # Fetch historical data (for previous weeks) with live data for current week
    team1_scores = fetch_historical_data(team1_entry_ids, current_event, player_names)
    team2_scores = fetch_historical_data(team2_entry_ids, current_event, player_names)

    # Check if Tabela has started
    has_current_data = any(
        bool(player['total_scores_by_week']) 
        for player in team1_scores + team2_scores
    )

    # Fetch live data ONCE for each event and reuse
    if current_event == display_event:
        # Same event for both live and analytics
        team1_analytics = fetch_live_data_optimized(team1_entry_ids, current_event, player_names)
        team2_analytics = fetch_live_data_optimized(team2_entry_ids, current_event, player_names)
        # For live data in table, use original order (NOT sorted)
        team1_live = fetch_live_data_optimized(team1_entry_ids, current_event, player_names)
        team2_live = fetch_live_data_optimized(team2_entry_ids, current_event, player_names)
    else:
        # Different events
        team1_live = fetch_live_data_optimized(team1_entry_ids, current_event, player_names)
        team2_live = fetch_live_data_optimized(team2_entry_ids, current_event, player_names)
        team1_analytics = fetch_live_data_optimized(team1_entry_ids, display_event, player_names)
        team2_analytics = fetch_live_data_optimized(team2_entry_ids, display_event, player_names)

    # Add season total points to ALL data and sort by total points (only if needed)
    if has_current_data:
        # Process team1_analytics data (Detalji tab - SORT BY SEASON TOTALS)
        if team1_analytics:
            for i, analytics_data in enumerate(team1_analytics):
                if i < len(team1_scores):
                    season_total = sum(team1_scores[i]['total_scores_by_week'].values())
                    analytics_data['season_total_points'] = season_total
                else:
                    analytics_data['season_total_points'] = 0
            # Sort team1_analytics by season total points (highest first)
            team1_analytics.sort(key=lambda x: x.get('season_total_points', 0), reverse=True)
        
        # Process team2_analytics data (Detalji tab - SORT BY SEASON TOTALS)
        if team2_analytics:
            for i, analytics_data in enumerate(team2_analytics):
                if i < len(team2_scores):
                    season_total = sum(team2_scores[i]['total_scores_by_week'].values())
                    analytics_data['season_total_points'] = season_total
                else:
                    analytics_data['season_total_points'] = 0
            # Sort team2_analytics by season total points (highest first)
            team2_analytics.sort(key=lambda x: x.get('season_total_points', 0), reverse=True)

        # Add season totals to live data but DON'T SORT (keep original order for table display)
        if team1_live:
            for i, live_data in enumerate(team1_live):
                if i < len(team1_scores):
                    season_total = sum(team1_scores[i]['total_scores_by_week'].values())
                    live_data['season_total_points'] = season_total
                else:
                    live_data['season_total_points'] = 0
            # DO NOT SORT team1_live - keep original order for table
        
        if team2_live:
            for i, live_data in enumerate(team2_live):
                if i < len(team2_scores):
                    season_total = sum(team2_scores[i]['total_scores_by_week'].values())
                    live_data['season_total_points'] = season_total
                else:
                    live_data['season_total_points'] = 0
            # DO NOT SORT team2_live - keep original order for table

    if has_current_data:
        team1_sums = calculate_team_sums(team1_scores)
        team2_sums = calculate_team_sums(team2_scores)
        team1_wins, team2_wins = calculate_team_wins(team1_sums, team2_sums)

        team1_points = sum(
            sum(week_data['total_scores_by_week'].get(week, 0) for week_data in team1_scores)
            for week in range(1, 39)
        )
        team2_points = sum(
            sum(week_data['total_scores_by_week'].get(week, 0) for week_data in team2_scores)
            for week in range(1, 39)
        )

        # Generate analytics
        analytics = generate_analytics(team1_scores, team2_scores, team1_sums, team2_sums)
    else:
        # No Tabela data
        team1_sums = {}
        team2_sums = {}
        team1_wins = team2_wins = 0
        team1_points = team2_points = 0
        analytics = None

    # Teams to color in Nosata liga tab
    colored_teams = ["Sport bar 22", "NEPOBEDIVI", "Hell Patrol", "ValjevoJeSvetoMesto", "grmilica", "mixXx007"]
    
    return render_template('index.html', 
                           team1_scores=team1_scores, 
                           team2_scores=team2_scores, 
                           team1_sums=team1_sums,
                           team2_sums=team2_sums, 
                           team1_wins=team1_wins, 
                           team2_wins=team2_wins,
                           team1_points=team1_points, 
                           team2_points=team2_points,
                           analytics=analytics,
                           has_current_data=has_current_data,
                           team1_live=team1_live,
                           team2_live=team2_live,
                           current_event=current_event,
                           team1_analytics=team1_analytics,
                           team2_analytics=team2_analytics,
                           display_event=display_event,
                           gw_status=gw_status_text,
                           league_name=league_name,
                           league_live_data=league_live_data,
                           colored_teams=colored_teams)

def calculate_team_wins(team1_sums, team2_sums):
    team1_wins = 0
    team2_wins = 0

    for week, team1_sum in team1_sums.items():
        team2_sum = team2_sums.get(week, 0)
        if team1_sum > team2_sum:
            team1_wins += 1
        elif team2_sum > team1_sum:
            team2_wins += 1

    return team1_wins, team2_wins


def get_previous_week_team(entry_id, event):
    """Get the team picks from the previous gameweek"""
    if event <= 1:
        return []
    
    try:
        prev_event = event - 1
        picks_url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/event/{prev_event:02d}/picks/"
        response = requests.get(picks_url)
        response.raise_for_status()
        picks_data = response.json()
        
        # Return only the starting XI (multiplier > 0)
        return [pick["element"] for pick in picks_data["picks"] if pick["multiplier"] > 0]
    except:
        return []

def calculate_transfer_points(entry_id, current_event, live_points, player_names):
    """Calculate points from new and sold players"""
    if current_event <= 1:
        return 0, 0  # No transfers to calculate for GW1
    
    try:
        # Get current week team
        current_picks_url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/event/{current_event:02d}/picks/"
        current_response = requests.get(current_picks_url)
        current_response.raise_for_status()
        current_picks = current_response.json()
        current_team = [pick["element"] for pick in current_picks["picks"] if pick["multiplier"] > 0]
        
        # Get previous week team
        previous_team = get_previous_week_team(entry_id, current_event)
        
        if not previous_team:
            return 0, 0
        
        # Find new players (in current but not in previous)
        new_players = [player for player in current_team if player not in previous_team]
        
        # Find sold players (in previous but not in current)
        sold_players = [player for player in previous_team if player not in current_team]
        
        # Calculate points from new players (current gameweek)
        new_player_points = sum(live_points.get(player_id, 0) for player_id in new_players)
        
        # For sold players, we'd need their points from the previous gameweek
        # This is more complex and would require fetching previous GW live data
        # For now, we'll return 0 for sold players' points
        sold_player_points = 0
        
        return new_player_points, sold_player_points
        
    except Exception as e:
        print(f"Error calculating transfer points for entry {entry_id}: {e}")
        return 0, 0

def apply_auto_substitutions(picks_data, live_data, bootstrap_data):
    """Apply FPL auto-substitution rules for players who didn't play (0 minutes)"""
    
    # Get player positions from bootstrap data
    player_positions = {}
    for element in bootstrap_data.get("elements", []):
        player_positions[element["id"]] = element["element_type"]
    
    # Get picks and separate starting XI from bench
    picks = picks_data.get("picks", [])
    starting_xi = [pick for pick in picks if pick["position"] <= 11]
    bench = [pick for pick in picks if pick["position"] > 11]
    
    # Sort bench by position (12, 13, 14, 15)
    bench.sort(key=lambda x: x["position"])
    
    substitutions_made = []
    
    # Check each starting XI player for 0 minutes AND finished game
    for pick in starting_xi[:]:  # Use slice to avoid modifying during iteration
        player_stats = get_player_live_stats(pick["element"], live_data)
        
        # Check if player has 0 minutes AND game is finished
        if player_stats["minutes"] == 0 and is_player_game_finished(pick["element"], live_data):
            # Find suitable substitute from bench
            substitute = find_suitable_substitute(bench, pick, player_positions, starting_xi)
            
            if substitute:
                # Make the substitution
                substitutions_made.append({
                    "out": pick["element"],
                    "in": substitute["element"],
                    "out_position": pick["position"],
                    "in_position": substitute["position"]
                })
                
                # Swap positions
                old_bench_pos = substitute["position"]
                substitute["position"] = pick["position"]
                pick["position"] = old_bench_pos
                
                # Remove substitute from bench and add to starting XI
                bench.remove(substitute)
                starting_xi = [p for p in picks if p["position"] <= 11]
    
    return starting_xi, bench

def get_player_live_stats(element_id, live_data):
    """Get player's live statistics including minutes and if game finished"""
    for element in live_data.get("elements", []):
        if element["id"] == element_id:
            return {
                "minutes": element["stats"]["minutes"],
                "starts": element["stats"]["starts"],
                "total_points": element["stats"]["total_points"]
            }
    return {"minutes": 0, "starts": 0, "total_points": 0}

def is_player_game_finished(element_id, live_data):
    """Check if player's game is finished"""
    # Get fixtures data from the live data
    fixtures_data = live_data.get("fixtures", [])
    
    # Find which fixture this player is in
    for fixture in fixtures_data:
        # Check if player is in home team stats
        for stat in fixture.get("stats", []):
            if stat["identifier"] == "minutes":
                # Check home team
                for player in stat.get("h", []):
                    if player["element"] == element_id:
                        return fixture.get("finished", False)
                # Check away team  
                for player in stat.get("a", []):
                    if player["element"] == element_id:
                        return fixture.get("finished", False)
    
    return False  # If player not found in any fixture, assume not finished

def find_suitable_substitute(bench, replaced_pick, player_positions, current_starting_xi):
    """Find a suitable substitute following FPL formation rules"""
    
    # Get the position of the player being replaced
    replaced_position = player_positions.get(replaced_pick["element"], 0)
    
    # Count current positions in starting XI
    position_counts = {1: 0, 2: 0, 3: 0, 4: 0}  # GK, DEF, MID, FWD
    for pick in current_starting_xi:
        pos = player_positions.get(pick["element"], 0)
        if pos in position_counts:
            position_counts[pos] += 1
    
    # FPL formation rules: min 1 GK, min 3 DEF, min 2 MID, min 1 FWD
    min_requirements = {1: 1, 2: 3, 3: 2, 4: 1}
    
    # Try to find substitute from bench (in bench order)
    for substitute in bench:
        substitute_position = player_positions.get(substitute["element"], 0)
        
        # Check if this substitution would maintain valid formation
        test_counts = position_counts.copy()
        test_counts[replaced_position] -= 1  # Remove replaced player
        test_counts[substitute_position] += 1  # Add substitute
        
        # Check if formation is still valid
        if all(test_counts[pos] >= min_requirements[pos] for pos in min_requirements):
            return substitute
    
    return None

@cache.memoize(timeout=CACHE_TIMEOUT_LIVE_POINTS)
def fetch_live_data_optimized(entry_ids, current_event=1, player_names=None):
    """Optimized fetch live data for current gameweek - cached for 3 minutes during active gameweek"""
    all_live_data = []
    
    # Use provided player names or fetch them if not provided
    if player_names is None:
        player_names = get_player_names()
    
    # First, get the live points for all players in this gameweek (ONCE)
    live_points = fetch_live_points(current_event)
    
    for entry_id in entry_ids:
        # Get this player's team picks for the current event
        picks_url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/event/{current_event:02d}/picks/"
        try:
            response = requests.get(picks_url)
            response.raise_for_status()
            picks_data = response.json()
            
            # Apply auto-substitutions before calculating points
            # Get bootstrap data for player positions
            bootstrap_data = get_bootstrap_data()
            
            # Check if we have full live data including fixtures
            live_api_url = f"https://fantasy.premierleague.com/api/event/{current_event:02d}/live/"
            live_response = requests.get(live_api_url)
            if live_response.status_code == 200:
                full_live_data = live_response.json()
                # Apply auto-substitutions 
                starting_xi, bench_picks = apply_auto_substitutions(picks_data, full_live_data, bootstrap_data)
            
            # Calculate transfer points
            new_player_points, sold_player_points = calculate_transfer_points(entry_id, current_event, live_points, player_names)
            
            # Calculate total points for this player
            total_points = 0
            bench_points = 0
            captain_points = 0
            all_players = []  # Store all playing players with their points
            
            for pick in picks_data["picks"]:
                element_id = pick["element"]
                multiplier = pick["multiplier"]
                is_captain = pick["is_captain"]
                
                # Get points for this element from live data
                element_points = live_points.get(element_id, 0)
                calculated_points = element_points * multiplier
                
                # Get player name from the mapping
                player_name = player_names.get(element_id, f"Player {element_id}")
                
                if multiplier > 0:  # Playing (not on bench)
                    total_points += calculated_points
                    
                    # Track captain points
                    if is_captain:
                        captain_points = calculated_points
                    
                    # Store all playing players with their ACTUAL points (including multipliers)
                    all_players.append({"name": player_name, "points": calculated_points})
                else:  # On bench
                    bench_points += element_points
            
            # Find all best and worst players based on actual points with multipliers
            if all_players:
                max_points = max(player["points"] for player in all_players)
                
                # For worst players, only consider those who actually played (points > 0)
                players_who_played = [player for player in all_players if player["points"] > 0]
                
                best_players = [player for player in all_players if player["points"] == max_points]
                
                if players_who_played:
                    min_points_played = min(player["points"] for player in players_who_played)
                    worst_players = [player for player in players_who_played if player["points"] == min_points_played]
                else:
                    # If no one scored any points, show that no one played
                    worst_players = [{"name": "Niko nije igrao", "points": 0}]
            else:
                best_players = [{"name": "N/A", "points": 0}]
                worst_players = [{"name": "N/A", "points": 0}]
            
            # Find best captain alternative
            best_captain_alternative = 0
            for pick in picks_data["picks"]:
                if pick["multiplier"] > 0 and not pick["is_captain"]:
                    element_points = live_points.get(pick["element"], 0)
                    potential_captain_points = element_points * 2
                    if potential_captain_points > best_captain_alternative:
                        best_captain_alternative = element_points
            
            live_data = {
                "entry_id": entry_id,
                "name": PLAYER_NAMES.get(entry_id, f"Player {entry_id}"),
                "total_points": total_points,
                "bench_points": bench_points,
                "captain_points": captain_points,
                "best_captain_alternative": best_captain_alternative,
                "best_players": best_players,
                "worst_players": worst_players,
                "transfers_cost": picks_data["entry_history"].get("event_transfers_cost", 0),
                "new_player_points": new_player_points,
                "sold_player_points": sold_player_points,
                "event": current_event
            }
            
            all_live_data.append(live_data)
            
        except Exception as e:
            print(f"Error fetching live data for entry {entry_id}: {e}")
            all_live_data.append({
                "entry_id": entry_id,
                "name": PLAYER_NAMES.get(entry_id, f"Player {entry_id}"),
                "total_points": 0,
                "bench_points": 0,
                "captain_points": 0,
                "best_captain_alternative": 0,
                "best_players": [{"name": "N/A", "points": 0}],
                "worst_players": [{"name": "N/A", "points": 0}],
                "transfers_cost": 0,
                "new_player_points": 0,
                "sold_player_points": 0,
                "event": current_event
            })
    
    return all_live_data

def fetch_live_data(entry_ids, current_event=1):
    """Legacy fetch live data function - kept for compatibility"""
    return fetch_live_data_optimized(entry_ids, current_event, None)

def fetch_live_points(event_number):
    """Fetch live points for all players in a specific gameweek - cached based on gameweek status"""
    # Dynamic cache timeout based on gameweek status
    gw_status = get_gameweek_status()
    if gw_status["status"] == "live":
        # During live gameweek, cache for shorter time
        cache_key = f"live_points_{event_number}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result
        
        result = _fetch_live_points_from_api(event_number)
        cache.set(cache_key, result, timeout=CACHE_TIMEOUT_LIVE_POINTS)  # 5 minutes during live
        return result
    else:
        # Finished gameweek, cache for longer
        return _fetch_live_points_cached_long(event_number)

@cache.memoize(timeout=7200)  # 2 hours for finished gameweeks
def _fetch_live_points_cached_long(event_number):
    """Cache live points for finished gameweeks for 2 hours"""
    return _fetch_live_points_from_api(event_number)

def _fetch_live_points_from_api(event_number):
    """Actual API call for live points - uses API bonus for finished games, calculates bonus for live games"""
    live_url = f"https://fantasy.premierleague.com/api/event/{event_number:02d}/live/"
    fixtures_url = f"https://fantasy.premierleague.com/api/fixtures/?event={event_number:02d}"
    
    try:
        # Get live data
        response = requests.get(live_url)
        response.raise_for_status()
        live_data = response.json()
        
        # Get fixtures data (cached)
        fixtures_data = get_fixtures_for_event(event_number)
        
        # Get bootstrap data (cached)
        bootstrap_data = get_bootstrap_data()
        
        # Create player to fixture mapping
        player_fixture_map = {}
        for fixture in fixtures_data:
            # Map all players from both teams to this fixture
            for stat in fixture.get("stats", []):
                if stat["identifier"] == "bps":
                    # Add home team players
                    for player in stat.get("h", []):
                        player_fixture_map[player["element"]] = fixture
                    # Add away team players  
                    for player in stat.get("a", []):
                        player_fixture_map[player["element"]] = fixture
        
        # Calculate bonus points for live games only
        live_bonus_points = calculate_bonus_points([
            fixture for fixture in fixtures_data 
            if not fixture.get("finished", False)
        ])
        
        # Create a mapping of element_id -> total_points
        live_points = {}
        for element in live_data["elements"]:
            element_id = element["id"]
            api_total = element["stats"]["total_points"]
            api_bonus = element["stats"]["bonus"]
            
            # Check if this player's game is finished
            player_fixture = player_fixture_map.get(element_id)
            if player_fixture and player_fixture.get("finished", False):
                # Game is finished - use API total (includes official bonus)
                live_points[element_id] = api_total
            else:
                # Game is live or not started - use calculated bonus
                base_points = api_total - api_bonus
                calculated_bonus = live_bonus_points.get(element_id, 0)
                live_points[element_id] = base_points + calculated_bonus
        
        return live_points
    except Exception as e:
        print(f"Error fetching live points for event {event_number}: {e}")
        return {}

def calculate_bonus_points(fixtures_data):
    """Calculate bonus points based on BPS from fixtures data with proper tie handling - processes live games only"""
    bonus_points = {}
    
    for fixture in fixtures_data:
        # Only process games that have started but are not finished (live games)
        # or finished_provisional games (recently finished but not yet official)
        if not (fixture.get("started", False) or fixture.get("finished_provisional", False)):
            continue
            
        # Find BPS stats
        for stat in fixture.get("stats", []):
            if stat["identifier"] == "bps":
                # Combine all players from both teams
                all_bps = []
                
                # Add home team players
                for player in stat.get("h", []):
                    all_bps.append({
                        "element": player["element"],
                        "bps": player["value"]
                    })
                
                # Add away team players
                for player in stat.get("a", []):
                    all_bps.append({
                        "element": player["element"],
                        "bps": player["value"]
                    })
                
                # Filter out players with 0 BPS and sort by BPS (highest first)
                all_bps = [player for player in all_bps if player["bps"] > 0]
                all_bps.sort(key=lambda x: x["bps"], reverse=True)
                
                if not all_bps:
                    continue
                
                # Group players by BPS score to handle ties properly
                bps_groups = {}
                for player in all_bps:
                    bps_score = player["bps"]
                    if bps_score not in bps_groups:
                        bps_groups[bps_score] = []
                    bps_groups[bps_score].append(player["element"])
                
                # Get unique BPS scores in descending order
                unique_bps_scores = sorted(bps_groups.keys(), reverse=True)
                
                # Award bonus points according to FPL tie rules
                awarded_players = 0
                
                for i, bps_score in enumerate(unique_bps_scores):
                    players_with_this_bps = bps_groups[bps_score]
                    
                    if awarded_players == 0:
                        # First place (or tie for first)
                        if len(players_with_this_bps) == 1:
                            # Single first place: 3 points
                            bonus_points[players_with_this_bps[0]] = bonus_points.get(players_with_this_bps[0], 0) + 3
                            awarded_players += 1
                        elif len(players_with_this_bps) == 2:
                            # Tie for first (2 players): both get 3 points, third gets 1
                            for player_id in players_with_this_bps:
                                bonus_points[player_id] = bonus_points.get(player_id, 0) + 3
                            awarded_players += 2
                            # Award 1 point to next best player if exists
                            if i + 1 < len(unique_bps_scores):
                                next_bps_players = bps_groups[unique_bps_scores[i + 1]]
                                bonus_points[next_bps_players[0]] = bonus_points.get(next_bps_players[0], 0) + 1
                                awarded_players += 1
                            break
                        else:
                            # Tie for first (3+ players): all get 3 points
                            for player_id in players_with_this_bps:
                                bonus_points[player_id] = bonus_points.get(player_id, 0) + 3
                            break
                    
                    elif awarded_players == 1:
                        # Second place (or tie for second)
                        if len(players_with_this_bps) == 1:
                            # Single second place: 2 points
                            bonus_points[players_with_this_bps[0]] = bonus_points.get(players_with_this_bps[0], 0) + 2
                            awarded_players += 1
                        else:
                            # Tie for second (2+ players): both get 2 points
                            for player_id in players_with_this_bps:
                                bonus_points[player_id] = bonus_points.get(player_id, 0) + 2
                            break
                    
                    elif awarded_players == 2:
                        # Third place (or tie for third)
                        if len(players_with_this_bps) == 1:
                            # Single third place: 1 point
                            bonus_points[players_with_this_bps[0]] = bonus_points.get(players_with_this_bps[0], 0) + 1
                        else:
                            # Tie for third (2+ players): all get 1 point
                            for player_id in players_with_this_bps:
                                bonus_points[player_id] = bonus_points.get(player_id, 0) + 1
                        break
                    
                    else:
                        # Already awarded all bonus points
                        break
                
                break  # Found BPS stats for this fixture
    
    return bonus_points

@cache.memoize(timeout=CACHE_TIMEOUT_HISTORICAL)
def fetch_historical_data(entry_ids, current_event=None, player_names=None):
    """Fetch historical data, using live data for current gameweek to ensure freshness - cached for 1 hour"""
    all_historical_data = []
    
    # Get current event if not provided
    if current_event is None:
        current_event = get_current_event()
    
    # Get live data for current gameweek
    if player_names is None:
        player_names = get_player_names()
    
    live_data_for_current = fetch_live_data_optimized(entry_ids, current_event, player_names)
    live_points_by_entry = {data["entry_id"]: data["total_points"] for data in live_data_for_current}

    for entry_id in entry_ids:
        url = "https://fantasy.premierleague.com/api/entry/" + str(entry_id) + "/history/"
        try:
            response = requests.get(url)
            data = response.json()

            # Check if historical data exists
            if "current" in data and data["current"]:
                current_data = data["current"]
                total_scores_by_week = {entry["event"]: (entry["points"]-entry["event_transfers_cost"]) for entry in current_data}
                
                # Update current gameweek with live data for freshness
                if entry_id in live_points_by_entry:
                    total_scores_by_week[current_event] = live_points_by_entry[entry_id]
            else:
                # No historical data available, but we can use live data for current week
                total_scores_by_week = {}
                if entry_id in live_points_by_entry:
                    total_scores_by_week[current_event] = live_points_by_entry[entry_id]

            all_historical_data.append({
                "entry_id": entry_id,
                "total_scores_by_week": total_scores_by_week,
                "name": PLAYER_NAMES.get(entry_id, f"Player {entry_id}")
            })
        except Exception as e:
            print(f"Error fetching data for entry {entry_id}: {e}")
            # Even on error, try to use live data for current week
            total_scores_by_week = {}
            if entry_id in live_points_by_entry:
                total_scores_by_week[current_event] = live_points_by_entry[entry_id]
            
            all_historical_data.append({
                "entry_id": entry_id,
                "total_scores_by_week": total_scores_by_week,
                "name": PLAYER_NAMES.get(entry_id, f"Player {entry_id}")
            })

    return all_historical_data

def calculate_team_sums(team_scores):
    team_sums = {}

    for entry_data in team_scores:
        entry_id = entry_data["entry_id"]
        total_scores_by_week = entry_data["total_scores_by_week"]

        for week, total_score in total_scores_by_week.items():
            if week not in team_sums:
                team_sums[week] = 0

            team_sums[week] += total_score

    return team_sums

def generate_analytics(team1_scores, team2_scores, team1_sums, team2_sums):
    """Generate fun analytics from the FPL data"""
    
    # Check if we have any data
    if not team1_sums or not team2_sums:
        return None
    
    # Combine all player data
    all_players = team1_scores + team2_scores
    
    # Calculate averages
    team1_weekly_scores = list(team1_sums.values())
    team2_weekly_scores = list(team2_sums.values())
    
    team1_avg = statistics.mean(team1_weekly_scores) if team1_weekly_scores else 0
    team2_avg = statistics.mean(team2_weekly_scores) if team2_weekly_scores else 0
    
    # Find best and worst team weeks
    best_week = {"team": "SAVEZNICI", "week": 1, "points": 0}
    worst_week = {"team": "SAVEZNICI", "week": 1, "points": float('inf')}
    
    for week, points in team1_sums.items():
        if points > best_week["points"]:
            best_week = {"team": "SAVEZNICI", "week": week, "points": points}
        if points < worst_week["points"]:
            worst_week = {"team": "SAVEZNICI", "week": week, "points": points}
    
    for week, points in team2_sums.items():
        if points > best_week["points"]:
            best_week = {"team": "GEJACI", "week": week, "points": points}
        if points < worst_week["points"]:
            worst_week = {"team": "GEJACI", "week": week, "points": points}
    
    # Player analytics
    player_stats = []
    for player in all_players:
        entry_id = player["entry_id"]
        scores = list(player["total_scores_by_week"].values())
        
        if scores:
            total = sum(scores)
            avg = statistics.mean(scores)
            consistency = statistics.stdev(scores) if len(scores) > 1 else 0
            
            # Determine trend (last 3 weeks vs previous 3)
            recent_scores = scores[-3:] if len(scores) >= 3 else scores
            previous_scores = scores[-6:-3] if len(scores) >= 6 else scores[:-3] if len(scores) > 3 else []
            
            trend = 'stable'
            if recent_scores and previous_scores:
                recent_avg = statistics.mean(recent_scores)
                previous_avg = statistics.mean(previous_scores)
                if recent_avg > previous_avg + 5:
                    trend = 'up'
                elif recent_avg < previous_avg - 5:
                    trend = 'down'
            
            player_stats.append({
                "entry_id": entry_id,
                "name": PLAYER_NAMES.get(entry_id, f"Player {entry_id}"),
                "total": total,
                "avg": avg,
                "consistency": consistency,
                "trend": trend
            })
    
    # Sort players by total points
    player_rankings = sorted(player_stats, key=lambda x: x["total"], reverse=True)
    
    # Find most consistent player (lowest standard deviation)
    most_consistent = min(player_stats, key=lambda x: x["consistency"]) if player_stats else {"name": "N/A", "consistency": 0, "avg": 0}
    
    # Find top scorer
    top_scorer = max(player_stats, key=lambda x: x["total"]) if player_stats else {"name": "N/A", "total": 0, "avg": 0}
    
    # Find biggest win margin
    biggest_margin = {"week": 1, "margin": 0, "winner": "TIE"}
    for week in team1_sums:
        if week in team2_sums:
            margin = abs(team1_sums[week] - team2_sums[week])
            if margin > biggest_margin["margin"]:
                winner = "SAVEZNICI" if team1_sums[week] > team2_sums[week] else "GEJACI"
                biggest_margin = {"week": week, "margin": margin, "winner": winner}
    
    # Team consistency (standard deviation)
    team1_consistency = statistics.stdev(team1_weekly_scores) if len(team1_weekly_scores) > 1 else 0
    team2_consistency = statistics.stdev(team2_weekly_scores) if len(team2_weekly_scores) > 1 else 0
    
    # Fun facts
    fun_facts = calculate_fun_facts(team1_sums, team2_sums, player_stats)
    
    return {
        "team1_avg": team1_avg,
        "team2_avg": team2_avg,
        "best_week": best_week,
        "worst_week": worst_week,
        "most_consistent": most_consistent,
        "top_scorer": top_scorer,
        "biggest_margin": biggest_margin,
        "player_rankings": player_rankings,
        "team1_consistency": team1_consistency,
        "team2_consistency": team2_consistency,
        "fun_facts": fun_facts
    }

def calculate_fun_facts(team1_sums, team2_sums, player_stats):
    """Calculate fun facts and streaks"""
    
    # Find win streaks
    team1_streak = 0
    team2_streak = 0
    max_team1_streak = 0
    max_team2_streak = 0
    
    # Find closest match
    closest_match = {"week": 1, "margin": float('inf')}
    
    for week in sorted(team1_sums.keys()):
        if week in team2_sums:
            # Win streaks
            if team1_sums[week] > team2_sums[week]:
                team1_streak += 1
                team2_streak = 0
                max_team1_streak = max(max_team1_streak, team1_streak)
            elif team2_sums[week] > team1_sums[week]:
                team2_streak += 1
                team1_streak = 0
                max_team2_streak = max(max_team2_streak, team2_streak)
            else:
                team1_streak = 0
                team2_streak = 0
            
            # Closest match
            margin = abs(team1_sums[week] - team2_sums[week])
            if margin < closest_match["margin"]:
                closest_match = {"week": week, "margin": margin}
    
    # Hottest and coldest streaks
    hottest_streak = f"SAVEZNICI ({max_team1_streak} wins)" if max_team1_streak >= max_team2_streak else f"GEJACI ({max_team2_streak} wins)"
    
    # Find player with most inconsistent performance
    most_inconsistent = max(player_stats, key=lambda x: x["consistency"]) if player_stats else None
    coldest_streak = f"{most_inconsistent['name']} (σ={most_inconsistent['consistency']:.1f})" if most_inconsistent else "None"
    
    # Biggest upset (when lower average team beats higher average team by large margin)
    biggest_upset = "No major upsets yet!"
    
    return {
        "hottest_streak": hottest_streak,
        "coldest_streak": coldest_streak,
        "closest_match": closest_match,
        "biggest_upset": biggest_upset
    }

@app.route('/api/team-details/<int:entry_id>')
def get_team_details(entry_id):
    """Get detailed team information for a specific player"""
    try:
        # Get current gameweek
        gw_status = get_gameweek_status()
        current_event = gw_status["event_id"]
        
        # Get player names
        player_names = get_player_names()
        
        # Get team picks for current gameweek
        picks_url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/event/{current_event:02d}/picks/"
        response = requests.get(picks_url)
        response.raise_for_status()
        picks_data = response.json()
        
        # Get live points data
        live_url = f"https://fantasy.premierleague.com/api/event/{current_event:02d}/live/"
        live_response = requests.get(live_url)
        live_response.raise_for_status()
        live_data = live_response.json()
        
        # Create element ID to points mapping
        element_points = {}
        for element in live_data.get("elements", []):
            element_points[element["id"]] = element["stats"]["total_points"]
        
        # Process team picks
        starting_xi = []
        bench = []
        total_points = 0
        bench_points = 0
        
        # Get active chip information
        active_chip = picks_data.get("active_chip")
        
        for pick in picks_data["picks"]:
            element_id = pick["element"]
            player_name = player_names.get(element_id, f"Player {element_id}")
            points = element_points.get(element_id, 0)
            multiplier = pick["multiplier"]
            actual_points = points * multiplier
            
            player_info = {
                "name": player_name,
                "points": actual_points,
                "multiplier": multiplier,
                "is_captain": pick.get("is_captain", False),
                "is_vice_captain": pick.get("is_vice_captain", False)
            }
            
            if multiplier > 0:  # Starting XI
                starting_xi.append(player_info)
                total_points += actual_points
            else:  # Bench
                bench.append(player_info)
                bench_points += points  # Bench points don't have multipliers
        
        return jsonify({
            "starting_xi": starting_xi,
            "bench": bench,
            "total_points": total_points,
            "bench_points": bench_points,
            "active_chip": active_chip
        })
        
    except Exception as e:
        print(f"Error getting team details for entry {entry_id}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/bootstrap-preload')
def bootstrap_preload():
    """Preload critical data for faster subsequent requests"""
    try:
        # Trigger caching of critical data
        get_bootstrap_data()
        get_current_event()
        get_player_names()
        return jsonify({"status": "preloaded"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/load-full-data')
def load_full_data():
    """Load full data asynchronously after initial page load"""
    try:
        team1_entry_ids = [4909598, 4658819, 3070732]
        team2_entry_ids = [2227937, 4895434, 729967]

        # Get current gameweek and its status
        gw_status = get_gameweek_status()
        current_event = gw_status["event_id"]
        display_event = gw_status["display_event"]
        gw_status_text = gw_status["status"]

        # Get player names
        player_names = get_player_names()

        # Load minimal essential data
        league_data = get_league_standings(LEAGUE_ID)
        
        # Return essential data for quick display
        return jsonify({
            "current_event": current_event,
            "display_event": display_event,
            "gw_status": gw_status_text,
            "league_name": league_data["league_name"],
            "has_data": True
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/load-tab-data/<tab_name>')
def load_tab_data(tab_name):
    """Load data for specific tab when user clicks on it"""
    try:
        team1_entry_ids = [4909598, 4658819, 3070732]
        team2_entry_ids = [2227937, 4895434, 729967]

        gw_status = get_gameweek_status()
        current_event = gw_status["event_id"]
        display_event = gw_status["display_event"]
        player_names = get_player_names()

        if tab_name == 'tabela':
            # Load Tabela data
            team1_scores = fetch_historical_data(team1_entry_ids, current_event, player_names)
            team2_scores = fetch_historical_data(team2_entry_ids, current_event, player_names)
            
            # Calculate team sums and wins
            team1_sums = calculate_team_sums(team1_scores)
            team2_sums = calculate_team_sums(team2_scores)
            team1_wins, team2_wins = calculate_team_wins(team1_sums, team2_sums)
            
            return jsonify({
                "tab": "tabela",
                "team1_sums": team1_sums,
                "team2_sums": team2_sums,
                "team1_wins": team1_wins,
                "team2_wins": team2_wins
            })
            
        elif tab_name == 'detalji':
            # Load Detalji data
            team1_analytics = fetch_live_data_optimized(team1_entry_ids, display_event, player_names)
            team2_analytics = fetch_live_data_optimized(team2_entry_ids, display_event, player_names)
            
            return jsonify({
                "tab": "detalji",
                "team1_analytics": team1_analytics,
                "team2_analytics": team2_analytics
            })
            
        elif tab_name == 'league':
            # Load League data
            league_data = get_league_standings(LEAGUE_ID)
            league_entries = league_data["entries"]
            league_name = league_data["league_name"]
            
            # Build league live data
            league_live_data = []
            if league_entries:
                for entry in league_entries[:10]:  # Limit to first 10 for speed
                    entry_id = entry["entry_id"]
                    players_data = get_players_to_play(entry_id, current_event, player_names)
                    captain_info = get_captain_info(entry_id, current_event, player_names)
                    
                    league_live_data.append({
                        "entry_id": entry_id,
                        "entry_name": entry["entry_name"],
                        "player_name": entry["player_name"],
                        "total_season_points": entry["total"],
                        "live_points": 0,  # Will be updated later if needed
                        "players_to_play": players_data["total"],
                        "players_waiting": players_data["waiting"],
                        "players_playing": players_data["playing"],
                        "players_to_play_count": len(players_data["total"]),
                        "has_live_players": len(players_data["playing"]) > 0,
                        "captain_info": captain_info
                    })
            
            return jsonify({
                "tab": "league",
                "league_name": league_name,
                "league_live_data": league_live_data
            })
        
        return jsonify({"status": "error", "message": "Unknown tab"})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/static/sw.js')
def service_worker():
    """Serve the service worker file"""
    return app.send_static_file('sw.js')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
