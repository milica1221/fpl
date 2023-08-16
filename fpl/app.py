from flask import Flask, render_template, request
import requests

app = Flask(__name__)

@app.route('/')
def index():
    team1_entry_ids = [6003724, 4650883, 1987295]
    team2_entry_ids = [2595484, 7046736, 3536412]

    team1_scores = fetch_historical_data(team1_entry_ids)
    team2_scores = fetch_historical_data(team2_entry_ids)

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

    return render_template('index.html', team1_scores=team1_scores, team2_scores=team2_scores, team1_sums=team1_sums,
                           team2_sums=team2_sums, team1_wins=team1_wins, team2_wins=team2_wins,
                           team1_points=team1_points, team2_points=team2_points)

def calculate_team_wins(team1_sums, team2_sums):
    team1_wins = 0
    team2_wins = 0

    for week, team1_sum in team1_sums.items():
        team2_sum = team2_sums.get(week, 0)  # Get the sum for team2 for the same week, default to 0 if not available
        if team1_sum > team2_sum:
            team1_wins += 1
        elif team2_sum > team1_sum:
            team2_wins += 1

    return team1_wins, team2_wins


def fetch_historical_data(entry_ids):
    all_historical_data = []

    for entry_id in entry_ids:
        # Make API request to fetch historical data for the given entry
        url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/history/"
        response = requests.get(url)
        data = response.json()

        # Process the data and extract scores for each week in current season
        current_data = data["current"]
        total_scores_by_week = {entry["event"]: entry["total_points"] for entry in current_data}

        all_historical_data.append({
            "entry_id": entry_id,
            "total_scores_by_week": total_scores_by_week
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

if __name__ == '__main__':
    app.run(debug=True)
