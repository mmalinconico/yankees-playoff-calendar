import json
from datetime import datetime
from pathlib import Path

import requests


YANKEES_TEAM_ID = 147

MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
MLB_VENUE_URL = "https://statsapi.mlb.com/api/v1/venues/{venue_id}"

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
        "hydrate": "broadcasts(all),seriesStatus",
    }

    response = requests.get(
        MLB_SCHEDULE_URL,
        params=params,
        timeout=30,
    )
    response.raise_for_status()

    return response.json()


def fetch_venue(venue_id):
    if not venue_id:
        return {}

    response = requests.get(
        MLB_VENUE_URL.format(venue_id=venue_id),
        params={
            "hydrate": "location",
        },
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()
    venues = data.get("venues", [])

    if not venues:
        return {}

    venue = venues[0]
    location = venue.get("location", {})

    return {
        "id": venue.get("id"),
        "name": venue.get("name"),
        "city": location.get("city"),
        "state": (
            location.get("stateAbbrev")
            or location.get("state")
        ),
    }


def get_tv_streaming_broadcasts(game):
    broadcasts = []

    for broadcast in game.get("broadcasts", []):
        broadcast_type = (broadcast.get("type") or "").upper()
        name = broadcast.get("name") or ""

        # MLB's feed mixes television, streaming, and radio broadcasts.
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


def normalize_game(game, venue_cache):
    teams = game.get("teams", {})

    away_info = teams.get("away", {})
    home_info = teams.get("home", {})

    away = away_info.get("team", {})
    home = home_info.get("team", {})

    if home.get("id") == YANKEES_TEAM_ID:
        opponent = away
        yankees_home = True
    else:
        opponent = home
        yankees_home = False

    schedule_venue = game.get("venue", {})
    venue_id = schedule_venue.get("id")

    if venue_id not in venue_cache:
        venue_cache[venue_id] = fetch_venue(venue_id)

    venue = venue_cache.get(venue_id, {}).copy()

    # Fall back to the schedule response if the venue lookup
    # does not provide these values.
    if not venue.get("name"):
        venue["name"] = schedule_venue.get("name")

    if not venue.get("id"):
        venue["id"] = venue_id

    status = game.get("status", {})
    series_status = game.get("seriesStatus", {})

    return {
        "gamePk": game.get("gamePk"),
        "gameDate": game.get("gameDate"),
        "officialDate": game.get("officialDate"),
        "startTimeTBD": status.get("startTimeTBD"),
        "status": status.get("detailedState"),
        "statusAbstract": status.get("abstractGameState"),
        "gameType": game.get("gameType"),
        "seriesDescription": game.get("seriesDescription"),
        "seriesGameNumber": game.get("seriesGameNumber"),
        "gamesInSeries": game.get("gamesInSeries"),
        "seriesStatus": series_status,
        "homeTeam": home.get("name"),
        "awayTeam": away.get("name"),
        "opponent": opponent.get("name"),
        "yankeesHome": yankees_home,
        "homeScore": home_info.get("score"),
        "awayScore": away_info.get("score"),
        "homeWinner": home_info.get("isWinner"),
        "awayWinner": away_info.get("isWinner"),
        "venue": venue,
        "broadcasts": get_tv_streaming_broadcasts(game),
    }


def main():
    season = current_season()

    print(f"Fetching Yankees postseason schedule for {season}...")

    data = fetch_schedule(season)

    games = []
    venue_cache = {}

    for date_block in data.get("dates", []):
        for game in date_block.get("games", []):
            games.append(
                normalize_game(
                    game,
                    venue_cache,
                )
            )

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
