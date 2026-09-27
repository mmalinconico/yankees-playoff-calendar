import json
from datetime import datetime
from pathlib import Path

import requests


YANKEES_TEAM_ID = 147
MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"

OUTPUT_FILE = Path("events.json")

# MLB postseason game-type codes:
# F = Wild Card
# D = Division Series
# L = League Championship Series
# W = World Series
POSTSEASON_GAME_TYPES = "F,D,L,W"


def current_season():
    return datetime.now().year


def fetch_schedule(season):
    params = {
        "sportId": 1,
        "teamId": YANKEES_TEAM_ID,
        "season": season,
        "gameTypes": POSTSEASON_GAME_TYPES,
        "hydrate": "broadcasts(all),seriesStatus,venue(location)",
    }

    response = requests.get(
        MLB_SCHEDULE_URL,
        params=params,
        timeout=30,
    )
    response.raise_for_status()

    return response.json()


def get_tv_streaming_broadcasts(game):
    broadcasts = []

    for broadcast in game.get("broadcasts", []):
        broadcast_type = (broadcast.get("type") or "").upper()
        name = broadcast.get("name") or ""

        # Keep television/streaming entries only.
        if broadcast_type not in {"TV", "STREAMING"}:
            continue

        # Exclude Spanish-language broadcasts/simulcasts.
        lower_name = name.lower()

        if (
            "universo" in lower_name
            or "telemundo" in lower_name
            or "univision" in lower_name
            or "tudn" in lower_name
        ):
            continue

        if name and name not in broadcasts:
            broadcasts.append(name)

    return broadcasts


def normalize_game(game):
    teams = game.get("teams", {})

    away = teams.get("away", {}).get("team", {})
    home = teams.get("home", {}).get("team", {})

    if home.get("id") == YANKEES_TEAM_ID:
        opponent = away
        yankees_home = True
    else:
        opponent = home
        yankees_home = False

    venue = game.get("venue", {})
    venue_location = venue.get("location", {})
    series_status = game.get("seriesStatus", {})

    return {
        "gamePk": game.get("gamePk"),
        "gameDate": game.get("gameDate"),
        "status": game.get("status", {}).get("detailedState"),
        "gameType": game.get("gameType"),
        "seriesDescription": game.get("seriesDescription"),
        "seriesGameNumber": game.get("seriesGameNumber"),
        "gamesInSeries": game.get("gamesInSeries"),
        "seriesStatus": series_status,
        "homeTeam": home.get("name"),
        "awayTeam": away.get("name"),
        "opponent": opponent.get("name"),
        "yankeesHome": yankees_home,
        "venue": {
            "id": venue.get("id"),
            "name": venue.get("name"),
            "city": venue_location.get("city"),
            "state": venue_location.get("stateAbbrev")
            or venue_location.get("state"),
        },
        "broadcasts": get_tv_streaming_broadcasts(game),
    }


def main():
    season = current_season()

    print(f"Fetching Yankees postseason schedule for {season}...")

    data = fetch_schedule(season)

    games = []

    for date_block in data.get("dates", []):
        for game in date_block.get("games", []):
            games.append(normalize_game(game))

    output = {
        "season": season,
        "team": "New York Yankees",
        "teamId": YANKEES_TEAM_ID,
        "games": games,
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, indent=2),
        encoding="utf-8",
    )

    print(f"Found {len(games)} postseason game(s).")
    print(f"Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
