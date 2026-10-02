import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


EVENTS_FILE = Path("events.json")
OUTPUT_FILE = Path("yankees-playoffs.ics")

GAME_DURATION = timedelta(hours=3)
RETENTION = timedelta(days=7)


def escape_ics(text):
    if text is None:
        return ""

    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def parse_game_date(value):
    if not value:
        return None

    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


def format_utc(dt):
    return dt.astimezone(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")


def format_date(dt):
    return dt.strftime("%Y%m%d")


def is_placeholder_time(game):
    """
    MLB uses :33 placeholder timestamps for postseason games
    whose actual start times have not yet been announced.

    Example:
    2026-10-07T07:33:00Z -> 3:33 AM Eastern

    A real MLB start time should replace this placeholder once
    the schedule is finalized.
    """
    start = parse_game_date(
        game.get("gameDate")
    )

    if start is None:
        return False

    return (
        not is_final_game(game)
        and start.minute == 33
    )


def is_final_game(game):
    abstract_status = (
        game.get("statusAbstract") or ""
    ).lower()

    detailed_status = (
        game.get("status") or ""
    ).lower()

    return (
        abstract_status == "final"
        or detailed_status in {
            "final",
            "game over",
            "completed early",
        }
    )


def get_game_winner(game):
    if not is_final_game(game):
        return None

    yankees_home = game.get("yankeesHome")

    if yankees_home:
        yankees_winner = game.get("homeWinner")
        opponent_winner = game.get("awayWinner")
        yankees_score = game.get("homeScore")
        opponent_score = game.get("awayScore")
    else:
        yankees_winner = game.get("awayWinner")
        opponent_winner = game.get("homeWinner")
        yankees_score = game.get("awayScore")
        opponent_score = game.get("homeScore")

    if yankees_winner is True:
        return "yankees"

    if opponent_winner is True:
        return "opponent"

    try:
        yankees_score = int(yankees_score)
        opponent_score = int(opponent_score)

        if yankees_score > opponent_score:
            return "yankees"

        if opponent_score > yankees_score:
            return "opponent"
    except (TypeError, ValueError):
        pass

    return None


def get_series_key(game):
    return game.get("gameType") or "postseason"


def get_series_total_games(game):
    total = game.get("gamesInSeries")

    if not total:
        total = (
            game.get("seriesStatus") or {}
        ).get("totalGames")

    try:
        return int(total)
    except (TypeError, ValueError):
        return None


def build_series_states(games):
    states = {}

    for game in games:
        key = get_series_key(game)
        total_games = get_series_total_games(game)

        if key not in states:
            states[key] = {
                "totalGames": total_games,
                "yankeesWins": 0,
                "opponentWins": 0,
                "countedGames": set(),
            }
        elif (
            not states[key]["totalGames"]
            and total_games
        ):
            states[key]["totalGames"] = total_games

        game_pk = game.get("gamePk")

        if game_pk in states[key]["countedGames"]:
            continue

        winner = get_game_winner(game)

        if winner == "yankees":
            states[key]["yankeesWins"] += 1
            states[key]["countedGames"].add(game_pk)

        elif winner == "opponent":
            states[key]["opponentWins"] += 1
            states[key]["countedGames"].add(game_pk)

    return states


def wins_needed(state):
    total_games = state.get("totalGames")

    if not total_games:
        return None

    return (total_games // 2) + 1


def series_is_clinched(state):
    needed = wins_needed(state)

    if not needed:
        return False

    return (
        state.get("yankeesWins", 0) >= needed
        or state.get("opponentWins", 0) >= needed
    )


def game_is_if_necessary(game, state):
    if is_final_game(game):
        return False

    if not state:
        return False

    needed = wins_needed(state)

    if not needed:
        return False

    try:
        game_number = int(
            game.get("seriesGameNumber")
        )
    except (TypeError, ValueError):
        return False

    yankees_wins = state.get("yankeesWins", 0)
    opponent_wins = state.get("opponentWins", 0)

    completed_games = (
        yankees_wins + opponent_wins
    )

    games_before_target = max(
        0,
        game_number - 1 - completed_games,
    )

    current_leader_wins = max(
        yankees_wins,
        opponent_wins,
    )

    return (
        current_leader_wins
        + games_before_target
        >= needed
    )


def get_series_name(game):
    return (
        game.get("seriesDescription")
        or "MLB Postseason"
    )


def get_game_number(
    game,
    if_necessary=False,
):
    number = game.get("seriesGameNumber")
    total = game.get("gamesInSeries")

    if number and total:
        text = f"Game {number} of {total}"
    elif number:
        text = f"Game {number}"
    else:
        return None

    if if_necessary:
        text += " (If Necessary)"

    return text


def get_matchup(game):
    away = game.get("awayTeam") or "TBD"
    home = game.get("homeTeam") or "TBD"

    return f"{away} @ {home}"


def get_summary(
    game,
    if_necessary=False,
    time_tbd=False,
):
    matchup = get_matchup(game)
    series = get_series_name(game)

    game_number = get_game_number(
        game,
        if_necessary=if_necessary,
    )

    parts = [
        matchup,
        series,
    ]

    if game_number:
        parts.append(game_number)

    if time_tbd:
        parts.append("TBD")

    return " — ".join(parts)


def get_description(
    game,
    if_necessary=False,
    time_tbd=False,
):
    lines = [
        f"Matchup: {get_matchup(game)}",
        f"Series: {get_series_name(game)}",
    ]

    game_number = get_game_number(
        game,
        if_necessary=if_necessary,
    )

    if game_number:
        lines.append(game_number)

    if time_tbd:
        lines.append("Start Time: TBD")

    broadcasts = game.get("broadcasts") or []

    if broadcasts:
        lines.append(
            f"TV/Streaming: {', '.join(broadcasts)}"
        )
    else:
        lines.append("TV/Streaming: TBA")

    status = game.get("status")

    if status:
        lines.append(f"Status: {status}")

    return "\\n".join(
        escape_ics(line)
        for line in lines
    )


def get_location(game):
    venue = game.get("venue") or {}

    name = venue.get("name")
    city = venue.get("city")
    state = venue.get("state")

    parts = []

    if name:
        parts.append(name)

    city_state = ", ".join(
        part
        for part in [city, state]
        if part
    )

    if city_state:
        parts.append(city_state)

    if parts:
        return ", ".join(parts)

    return "TBA"


def should_keep_game(
    game,
    now,
    series_state,
):
    start = parse_game_date(
        game.get("gameDate")
    )

    if start is None:
        return False

    detailed_status = (
        game.get("status") or ""
    ).lower()

    if detailed_status in {
        "cancelled",
        "canceled",
    }:
        return False

    if (
        series_state
        and series_is_clinched(series_state)
        and not is_final_game(game)
    ):
        return False

    if is_placeholder_time(game):
        return start.date() >= (
            now - RETENTION
        ).date()

    end = start + GAME_DURATION

    return end + RETENTION >= now


def build_event(
    game,
    now,
    if_necessary=False,
):
    start = parse_game_date(
        game.get("gameDate")
    )

    if start is None:
        return None

    game_pk = game.get("gamePk")

    uid = (
        f"yankees-playoffs-{game_pk}"
        "@mmalinconico.github.io"
    )

    time_tbd = is_placeholder_time(game)

    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{format_utc(now)}",
    ]

    if time_tbd:
        event_date = start.date()

        next_date = (
            event_date + timedelta(days=1)
        )

        lines.extend(
            [
                (
                    "DTSTART;VALUE=DATE:"
                    + event_date.strftime("%Y%m%d")
                ),
                (
                    "DTEND;VALUE=DATE:"
                    + next_date.strftime("%Y%m%d")
                ),
            ]
        )
    else:
        end = start + GAME_DURATION

        lines.extend(
            [
                f"DTSTART:{format_utc(start)}",
                f"DTEND:{format_utc(end)}",
            ]
        )

    lines.extend(
        [
            (
                "SUMMARY:"
                + escape_ics(
                    get_summary(
                        game,
                        if_necessary=if_necessary,
                        time_tbd=time_tbd,
                    )
                )
            ),
            (
                "LOCATION:"
                + escape_ics(
                    get_location(game)
                )
            ),
            (
                "DESCRIPTION:"
                + get_description(
                    game,
                    if_necessary=if_necessary,
                    time_tbd=time_tbd,
                )
            ),
            "END:VEVENT",
        ]
    )

    return lines


def main():
    if not EVENTS_FILE.exists():
        raise FileNotFoundError(
            f"{EVENTS_FILE} does not exist. "
            "Run fetch_events.py first."
        )

    data = json.loads(
        EVENTS_FILE.read_text(
            encoding="utf-8"
        )
    )

    now = datetime.now(timezone.utc)

    calendar_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        (
            "PRODID:-//Matt Malinconico//"
            "Yankees Playoff Calendar//EN"
        ),
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        (
            "X-WR-CALNAME:"
            "Yankees Playoff Calendar"
        ),
        (
            "X-WR-TIMEZONE:"
            "America/New_York"
        ),
    ]

    games = data.get("games", [])

    games.sort(
        key=lambda game:
        game.get("gameDate") or ""
    )

    series_states = build_series_states(
        games
    )

    included = 0

    for game in games:
        series_key = get_series_key(game)

        series_state = series_states.get(
            series_key
        )

        if not should_keep_game(
            game,
            now,
            series_state,
        ):
            continue

        if_necessary = game_is_if_necessary(
            game,
            series_state,
        )

        event_lines = build_event(
            game,
            now,
            if_necessary=if_necessary,
        )

        if event_lines:
            calendar_lines.extend(
                event_lines
            )
            included += 1

    calendar_lines.append(
        "END:VCALENDAR"
    )

    OUTPUT_FILE.write_text(
        "\r\n".join(calendar_lines)
        + "\r\n",
        encoding="utf-8",
    )

    print(f"Wrote {OUTPUT_FILE}")
    print(
        f"Included {included} "
        "postseason game(s)."
    )


if __name__ == "__main__":
    main()