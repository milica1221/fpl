from flask import Flask, render_template, request
import requests

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/calculate', methods=['POST'])
def calculate():
    team1_players = request.form.getlist('team1_player')
    team2_players = request.form.getlist('team2_player')

    import requests

    API_TOKEN = "YOUR_API_TOKEN"
    BASE_URL = "https://fantasy.premierleague.com/api/"

    def fetch_player_data(player_ids):
        player_data = []
        for player_id in player_ids:
            url = f"{BASE_URL}element-summary/{player_id}/"
            response = requests.get(url)
            data = response.json()
            player_data.append(data)
        return player_data

    def calculate_team_points(player_data):
        total_points = 0
        for player in player_data:
            total_points += player["history"][0]["total_points"]  # Change index if needed
        return total_points

    # Replace with actual player IDs
    team1_player_ids = [123, 456, 789]
    team2_player_ids = [987, 654, 321]

    team1_data = fetch_player_data(team1_player_ids)
    team2_data = fetch_player_data(team2_player_ids)

    team1_points = calculate_team_points(team1_data)
    team2_points = calculate_team_points(team2_data)

    if team1_points > team2_points:
        leading_team = "Team 1"
    elif team2_points > team1_points:
        leading_team = "Team 2"
    else:
        leading_team = "Both teams are tied"

    print(f"{leading_team} is leading.")

    return render_template('results.html', team1_points=team1_points, team2_points=team2_points)

if __name__ == '__main__':
    app.run(debug=True)
