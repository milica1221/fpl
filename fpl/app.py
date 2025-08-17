from flask import Flask, render_template, jsonify
import requests

app = Flask(__name__)

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

# Global variables for cached data
GAMEWEEK_STATUS = {}
BOOTSTRAP_DATA = {}
EVENTS_DATA = []
PLAYERS_DATA = []
FOOTBALL_PLAYER_NAMES = {}
CURRENT_EVENT = 1
DISPLAY_EVENT = 1
GW_STATUS_TEXT = "not_started"

# Team IDs
TEAM1_ENTRY_IDS = [4909598, 4658819, 3070732]
TEAM2_ENTRY_IDS = [2227937, 4895434, 729967]


def initialize_global_data():    
    try:
        print("🔄 Initializing global data...")

        global GAMEWEEK_STATUS, BOOTSTRAP_DATA, EVENTS_DATA, PLAYERS_DATA, FOOTBALL_PLAYER_NAMES
        global CURRENT_EVENT, DISPLAY_EVENT, GW_STATUS_TEXT

        # Load bootstrap data
        BOOTSTRAP_DATA = get_bootstrap_data()
        EVENTS_DATA = BOOTSTRAP_DATA.get("events", [])
        PLAYERS_DATA = BOOTSTRAP_DATA.get("elements", [])
        
        # Get current gameweek status
        GAMEWEEK_STATUS = get_gameweek_status(EVENTS_DATA)
        CURRENT_EVENT = GAMEWEEK_STATUS["event_id"]
        DISPLAY_EVENT = GAMEWEEK_STATUS["display_event"]
        GW_STATUS_TEXT = GAMEWEEK_STATUS["status"]
        
        # Get player names and cache them
        FOOTBALL_PLAYER_NAMES = get_player_names(PLAYERS_DATA)
        
        print(f"✅ Global data initialized - Current Event: {CURRENT_EVENT}, Status: {GW_STATUS_TEXT}")
        
    except Exception as e:
        print(f"❌ Error initializing global data: {e}")
        GAMEWEEK_STATUS = {"event_id": 1, "status": "not_started", "display_event": 1}
        CURRENT_EVENT = 1
        DISPLAY_EVENT = 1
        GW_STATUS_TEXT = "not_started"
        BOOTSTRAP_DATA = {}
        EVENTS_DATA = []
        PLAYERS_DATA = []
        FOOTBALL_PLAYER_NAMES = {}

def get_gameweek_status(events):
    """Get current gameweek status"""
    try:
        current_event_id = None
        current_event_data = None

        for event in events:
            if event["is_current"]:
                current_event_id = event["id"]
                current_event_data = event
                break

        if not current_event_data:
            return {"event_id": 1, "status": "not_started", "display_event": 1}
        
        if current_event_data["finished"]:
            return {"event_id": current_event_id, "status": "finished", "display_event": current_event_id}
        elif current_event_data["is_current"]:
            return {"event_id": current_event_id, "status": "live", "display_event": current_event_id}
        else:
            last_finished_event = 1
            for event in events:
                if event["finished"]:
                    last_finished_event = event["id"]
            
            return {"event_id": current_event_id, "status": "not_started", "display_event": last_finished_event}
        
    except Exception as e:
        print(f"Error getting gameweek status: {e}")
        return {"event_id": 1, "status": "not_started", "display_event": 1}

def get_player_names(elements):
    """Get all player names from FPL API - cached for 1 hour"""
    try:
        player_names = {}
        for element in elements:
            full_name = f"{element['first_name']} {element['second_name']}"
            if len(element['web_name']) < len(full_name) and element['web_name']:
                player_names[element['id']] = element['web_name']
            else:
                player_names[element['id']] = full_name
        
        return player_names
    except Exception as e:
        print(f"Error getting player names: {e}")
        return {}

def get_league_standings(league_id):
    """Get league standings from FPL API - cached for 10 minutes"""
    try:
        response = requests.get(f"https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/")
        response.raise_for_status()
        data = response.json()
        
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

def get_fixtures_for_event(event_id):
    try:
        response = requests.get(f"https://fantasy.premierleague.com/api/fixtures/?event={event_id}")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error getting fixtures for event {event_id}: {e}")
        return []

def get_players_to_play(entry_id, player_names, picks_data, bootstrap_data, fixtures_data):
    """Get list of players yet to play for a specific team with current playing status"""
    try:        
        player_to_team = {}
        for element in bootstrap_data.get("elements", []):
            player_to_team[element["id"]] = element["team"]
        
        team_status = {}  
        for fixture in fixtures_data:
            team_h = fixture["team_h"]
            team_a = fixture["team_a"]
            
            # Check if game is finished (official or provisional)
            is_finished = (
                fixture.get("finished", False) or 
                (fixture.get("finished_provisional", False) and fixture.get("minutes", 0) >= 90)
            )
            
            if is_finished:
                status = "finished"
            elif fixture.get("started", False):
                status = "live"
            else:
                status = "not_started"
            
            team_status[team_h] = status
            team_status[team_a] = status
        
        players_to_play = []
        currently_playing = []
        
        for pick in picks_data["picks"]:
            if pick["multiplier"] > 0:
                element_id = pick["element"]
                player_team = player_to_team.get(element_id)
                team_match_status = team_status.get(player_team, "not_started")
                
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
                        "status": team_match_status
                    }
                    
                    if team_match_status == "live":
                        currently_playing.append(player_info)
                    else:
                        players_to_play.append(player_info)
        
        return {
            "waiting": players_to_play, 
            "playing": currently_playing, 
            "total": players_to_play + currently_playing
        }
    except Exception as e:
        print(f"Error getting players to play for entry {entry_id}: {e}")
        return {
            "waiting": [],
            "playing": [],
            "total": []
        }

def get_captain_info(entry_id, player_names, picks_data, bootstrap_data, live_data, fixtures_data):
    """Get captain information for a specific team"""
    try:     
        player_to_team = {}
        for element in bootstrap_data.get("elements", []):
            player_to_team[element["id"]] = element["team"]
        
        finished_teams = set()
        playing_teams = set()
        for fixture in fixtures_data:
            is_finished = (
                fixture.get("finished", False) or 
                (fixture.get("finished_provisional", False) and fixture.get("minutes", 0) >= 90)
            )
            
            if is_finished:
                finished_teams.add(fixture["team_h"])
                finished_teams.add(fixture["team_a"])
            elif fixture.get("started", False):
                playing_teams.add(fixture["team_h"])
                playing_teams.add(fixture["team_a"])
        
        captain_element_id = None
        for pick in picks_data["picks"]:
            if pick["is_captain"]:
                captain_element_id = pick["element"]
                break
        
        if captain_element_id:
            captain_name = player_names.get(captain_element_id, f"Player {captain_element_id}")
            captain_team = player_to_team.get(captain_element_id)
            
            captain_base_points = live_data.get(captain_element_id, 0)
            captain_points = captain_base_points * 2  # Captain gets double points
            
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

def get_bootstrap_data():
    """Get bootstrap data from API"""
    try:
        url = "https://fantasy.premierleague.com/api/bootstrap-static/"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        return data
    
    except Exception as e:
        print(f"Error getting bootstrap data: {e}")
        return {}

@app.route('/')
def index():  
    """Render the main index page with all data"""   
    initialize_global_data()
    
    data = BOOTSTRAP_DATA
    current_event = CURRENT_EVENT
    display_event = DISPLAY_EVENT
    gw_status_text = GW_STATUS_TEXT
    player_names = FOOTBALL_PLAYER_NAMES
    
    league_data = get_league_standings(LEAGUE_ID)
    league_entries = league_data["entries"]
    league_name = league_data["league_name"]
    
    live_points_current_event = fetch_live_points(current_event)
    live_points_display_event = fetch_live_points(display_event)
    
    fixtures_data = get_fixtures_for_event(current_event)

    league_live_data = []
    if league_entries:
        print("🔄 Fetching live data for league entries...")
        league_entry_ids = [entry["entry_id"] for entry in league_entries]
        
        picks = {}
        for i, entry in enumerate(league_entries):
            picks_url = f"https://fantasy.premierleague.com/api/entry/{entry["entry_id"]}/event/{current_event:02d}/picks/"
            response = requests.get(picks_url)
            response.raise_for_status()
            picks_data = response.json()
            picks[entry["entry_id"]] = picks_data

        live_data_optimized = fetch_live_data_optimized(league_entry_ids, current_event, player_names, data, live_points_current_event, picks)

        league_live_points = live_data_optimized if live_data_optimized else []
        

        for i, entry in enumerate(league_entries):
            entry_id = entry["entry_id"]    
                    
            live_data = next((data for data in league_live_points if data["entry_id"] == entry_id), None)
            
            picks_data = picks.get(entry_id, {})
            players_data = get_players_to_play(entry_id, player_names, picks_data, data, fixtures_data)
            
            captain_info = get_captain_info(entry_id, player_names, picks_data, data, live_points_current_event, fixtures_data)
            
            live_points_for_gw = live_data["total_points"] if live_data else 0
            
            league_live_data.append({
                "entry_id": entry_id,
                "entry_name": entry["entry_name"],
                "player_name": entry["player_name"],
                "live_points": live_points_for_gw,  
                "players_to_play": players_data["total"],  
                "players_waiting": players_data["waiting"],
                "players_playing": players_data["playing"],  
                "players_to_play_count": len(players_data["total"]),
                "has_live_players": len(players_data["playing"]) > 0, 
                "captain_info": captain_info
            })
    
    league_live_data.sort(key=lambda x: x["live_points"], reverse=True)

    print("🔄 Fetching live data for teams...")
    
    team1_live_points = [entry for entry in live_data_optimized if entry['entry_id'] in TEAM1_ENTRY_IDS]
    team2_live_points = [entry for entry in live_data_optimized if entry['entry_id'] in TEAM2_ENTRY_IDS]
    
    historical_data = fetch_historical_data(TEAM1_ENTRY_IDS + TEAM2_ENTRY_IDS, current_event, live_points_current_event)

    team1_scores = [entry for entry in historical_data if entry['entry_id'] in TEAM1_ENTRY_IDS]
    team2_scores = [entry for entry in historical_data if entry['entry_id'] in TEAM2_ENTRY_IDS]

    # Check if Tabela has started
    has_current_data = any(
        bool(player['total_scores_by_week']) 
        for player in team1_scores + team2_scores
    )
    
    display_live_data = fetch_live_data_optimized(TEAM1_ENTRY_IDS + TEAM2_ENTRY_IDS, display_event, player_names, data, live_points_display_event, picks)


    print(f"🔄 Has current data: {has_current_data}")
    if current_event == display_event:
        team1_analytics = team1_live_points
        team2_analytics = team2_live_points
        team1_live = team1_live_points
        team2_live = team2_live_points
    else:
        team1_live = team1_live_points
        team2_live = team2_live_points
        team1_analytics = [entry for entry in display_live_data if entry['entry_id'] in TEAM1_ENTRY_IDS]
        team2_analytics = [entry for entry in display_live_data if entry['entry_id'] in TEAM2_ENTRY_IDS]

    if has_current_data:
        if team1_analytics:
            for i, analytics_data in enumerate(team1_analytics):
                if i < len(team1_scores):
                    season_total = sum(team1_scores[i]['total_scores_by_week'].values())
                    analytics_data['season_total_points'] = season_total
                else:
                    analytics_data['season_total_points'] = 0
            team1_analytics.sort(key=lambda x: x.get('total_points', 0), reverse=True)
        
        if team2_analytics:
            for i, analytics_data in enumerate(team2_analytics):
                if i < len(team2_scores):
                    season_total = sum(team2_scores[i]['total_scores_by_week'].values())
                    analytics_data['season_total_points'] = season_total
                else:
                    analytics_data['season_total_points'] = 0
            team2_analytics.sort(key=lambda x: x.get('total_points', 0), reverse=True)

        if team1_live:
            for i, live_data in enumerate(team1_live):
                if i < len(team1_scores):
                    season_total = sum(team1_scores[i]['total_scores_by_week'].values())
                    live_data['season_total_points'] = season_total
                else:
                    live_data['season_total_points'] = 0
        
        if team2_live:
            for i, live_data in enumerate(team2_live):
                if i < len(team2_scores):
                    season_total = sum(team2_scores[i]['total_scores_by_week'].values())
                    live_data['season_total_points'] = season_total
                else:
                    live_data['season_total_points'] = 0

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

    else:
        team1_sums = {}
        team2_sums = {}
        team1_wins = team2_wins = 0
        team1_points = team2_points = 0

    colored_teams = ["Sport bar 22", "NEPOBEDIVI", "Hell Patrol", "ValjevoJeSvetoMesto", "grmilica", "mixXx007"]
    
    print("🔄 Rendering index template with data...")
    
    return render_template('index.html', 
                           team1_scores=team1_scores, 
                           team2_scores=team2_scores, 
                           team1_sums=team1_sums,
                           team2_sums=team2_sums, 
                           team1_wins=team1_wins, 
                           team2_wins=team2_wins,
                           team1_points=team1_points, 
                           team2_points=team2_points,
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
                           colored_teams=colored_teams,
                           our_team_ids=[4909598, 4658819, 3070732, 2227937, 4895434, 729967])  # Our 6 players for glowing effect

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

def calculate_transfer_points(entry_id, current_event, live_points, current_picks):
    """Calculate points from new and sold players"""
    if current_event <= 1:
        return 0, 0  # No transfers to calculate for GW1
    
    try:
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

def fetch_live_data_optimized(entry_ids, current_event=1, player_names=None, bootstrap_data=None, live_points=None, picks=None):
    """Optimized fetch live data for current gameweek - cached for 3 minutes during active gameweek"""
    all_live_data = []
    
    for entry_id in entry_ids:
        try:
            picks_data = picks.get(entry_id, {})
            
            full_live_data = live_points
            starting_xi, bench_picks = apply_auto_substitutions(picks_data, full_live_data, bootstrap_data)
            
            # Calculate transfer points
            new_player_points, sold_player_points = calculate_transfer_points(entry_id, current_event, live_points, picks_data)
            
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
            
            
            live_data = {
                "entry_id": entry_id,
                "name": PLAYER_NAMES.get(entry_id, f"Player {entry_id}"),
                "total_points": total_points,
                "bench_points": bench_points,
                "captain_points": captain_points,
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
                "best_players": [{"name": "N/A", "points": 0}],
                "worst_players": [{"name": "N/A", "points": 0}],
                "transfers_cost": 0,
                "new_player_points": 0,
                "sold_player_points": 0,
                "event": current_event
            })
    
    return all_live_data

def fetch_live_points(event_number):
    """Fetch live points for all players in a specific gameweek - cached based on gameweek status"""
    live_url = f"https://fantasy.premierleague.com/api/event/{event_number:02d}/live/"
    
    try:
        # Get live data
        response = requests.get(live_url)
        response.raise_for_status()
        live_data = response.json()
        
        fixtures_data = get_fixtures_for_event(event_number)
        
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
            
            # Check if this player's game is finished (official or provisional)
            player_fixture = player_fixture_map.get(element_id)
            is_game_finished = (
                player_fixture and (
                    player_fixture.get("finished", False) or 
                    (player_fixture.get("finished_provisional", False) and player_fixture.get("minutes", 0) >= 90)
                )
            )
            
            if is_game_finished:
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
        # Check if game is truly finished (official or provisional with 90+ minutes)
        is_finished = (
            fixture.get("finished", False) or 
            (fixture.get("finished_provisional", False) and fixture.get("minutes", 0) >= 90)
        )
        
        if not fixture.get("started", False) or is_finished:
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

def fetch_historical_data(entry_ids, current_event=None, live_points_by_entry=None):
    all_historical_data = []

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
        total_scores_by_week = entry_data["total_scores_by_week"]

        for week, total_score in total_scores_by_week.items():
            if week not in team_sums:
                team_sums[week] = 0

            team_sums[week] += total_score

    return team_sums

@app.route('/api/team-details/<int:entry_id>')
def get_team_details(entry_id):
    """Get detailed team information for a specific player"""
    try:
        current_event = CURRENT_EVENT
        player_names = FOOTBALL_PLAYER_NAMES
        
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
                "points": points if multiplier == 0 else actual_points,  # Show base points for bench, actual points for starting XI
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

    
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
