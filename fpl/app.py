from flask import Flask, render_template, request
import requests
import statistics

app = Flask(__name__)

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

def get_current_event():
    """Get the current gameweek number from FPL API"""
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

def get_gameweek_status():
    """Get current gameweek status - is it live, finished, or not started"""
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

def get_player_names():
    """Get all player names from FPL API"""
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

def get_league_standings(league_id):
    """Get league standings from FPL API"""
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
    """Get list of players yet to play for a specific team"""
    try:
        # Get current week team picks
        picks_url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/event/{current_event:02d}/picks/"
        response = requests.get(picks_url)
        response.raise_for_status()
        picks_data = response.json()
        
        # Get fixtures for current event to check which games have finished
        fixtures_url = f"https://fantasy.premierleague.com/api/fixtures/?event={current_event:02d}"
        fixtures_response = requests.get(fixtures_url)
        fixtures_response.raise_for_status()
        fixtures_data = fixtures_response.json()
        
        # Get bootstrap data to map players to teams
        bootstrap_response = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/")
        bootstrap_response.raise_for_status()
        bootstrap_data = bootstrap_response.json()
        
        # Create player to team mapping
        player_to_team = {}
        for element in bootstrap_data["elements"]:
            player_to_team[element["id"]] = element["team"]
        
        # Create team to fixture mapping (which games are finished)
        finished_teams = set()
        for fixture in fixtures_data:
            if fixture.get("finished", False):
                finished_teams.add(fixture["team_h"])
                finished_teams.add(fixture["team_a"])
        
        # Find players yet to play
        players_to_play = []
        for pick in picks_data["picks"]:
            if pick["multiplier"] > 0:  # Only starting XI
                element_id = pick["element"]
                player_team = player_to_team.get(element_id)
                
                # If player's team hasn't finished their game yet
                if player_team and player_team not in finished_teams:
                    player_name = player_names.get(element_id, f"Player {element_id}")
                    is_captain = pick["is_captain"]
                    is_vice_captain = pick["is_vice_captain"]
                    is_triple_captain = pick.get("is_triple_captain", False)
                    
                    players_to_play.append({
                        "name": player_name,
                        "is_captain": is_captain,
                        "is_vice_captain": is_vice_captain,
                        "is_triple_captain": is_triple_captain,
                        "multiplier": pick["multiplier"]
                    })
        
        return players_to_play
    except Exception as e:
        print(f"Error getting players to play for entry {entry_id}: {e}")
        return []

@app.route('/')
def index():
    team1_entry_ids = [4909598, 4658819, 3070732]
    team2_entry_ids = [2227937, 4895434, 729967]

    # Get current gameweek and its status
    gw_status = get_gameweek_status()
    current_event = gw_status["event_id"]
    display_event = gw_status["display_event"]  # This is what Detalji tab will show
    gw_status_text = gw_status["status"]

    # Get player names ONCE and cache them
    player_names = get_player_names()

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
        
        # Combine league standings with fresh data
        for i, entry in enumerate(league_entries):
            entry_id = entry["entry_id"]
            # Find corresponding fresh historical data
            fresh_data = next((data for data in league_fresh_data if data["entry_id"] == entry_id), None)
            
            # Get players yet to play for this team
            players_to_play = get_players_to_play(entry_id, current_event, player_names)
            
            if fresh_data:
                # Calculate total season points using fresh data (including live current gameweek)
                fresh_total_points = sum(fresh_data["total_scores_by_week"].values())
                current_gw_points = fresh_data["total_scores_by_week"].get(current_event, 0)
                
                league_live_data.append({
                    "entry_id": entry_id,
                    "entry_name": entry["entry_name"],
                    "player_name": entry["player_name"],
                    "total_season_points": fresh_total_points,  # Use fresh total
                    "live_points": current_gw_points,
                    "players_to_play": players_to_play,
                    "players_to_play_count": len(players_to_play)
                })
            else:
                # Fallback to old data if fresh data not available
                league_live_data.append({
                    "entry_id": entry_id,
                    "entry_name": entry["entry_name"],
                    "player_name": entry["player_name"],
                    "total_season_points": entry["total"],
                    "live_points": 0,
                    "players_to_play": players_to_play,
                    "players_to_play_count": len(players_to_play)
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

def fetch_live_data_optimized(entry_ids, current_event=1, player_names=None):
    """Optimized fetch live data for current gameweek - accepts pre-fetched player names"""
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
    """Fetch live points for all players in a specific gameweek - uses API bonus for finished games, calculates bonus for live games"""
    live_url = f"https://fantasy.premierleague.com/api/event/{event_number:02d}/live/"
    fixtures_url = f"https://fantasy.premierleague.com/api/fixtures/?event={event_number:02d}"
    
    try:
        # Get live data and fixtures data
        response = requests.get(live_url)
        response.raise_for_status()
        live_data = response.json()
        
        fixtures_response = requests.get(fixtures_url)
        fixtures_response.raise_for_status()
        fixtures_data = fixtures_response.json()
        
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

def fetch_historical_data(entry_ids, current_event=None, player_names=None):
    """Fetch historical data, using live data for current gameweek to ensure freshness"""
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
