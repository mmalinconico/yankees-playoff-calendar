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

    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def format_utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def get_series_name(game):
    return game.get("seriesDescription") or "MLB Postseason"


def get_game_number(game):
    number = game.get("seriesGameNumber")
    total = game.get("gamesInSeries")

    if number and total:
        return f"Game {number} of {total}"

    if number:
        return f"Game {number}"

    return None


def get_matchup(game):
    away = game.get("awayTeam") or "TBD"
    home = game.get("homeTeam") or "TBD"

    return f"{away} at {home}"


def get_summary(game):
    opponent = game.get("opponent") or "TBD"
    series = get_series_name(game)
    game_number = get_game_number(game)

    parts = [f"Yankees vs. {opponent}", series]

    if game_number:
        parts.append(game_number)

    return " — ".join(parts)


def get_description(game):
    lines = [
        f"Matchup: {get_matchup(game)}",
        f"Series: {get_series_name(game)}",
    ]

    game_number = get_game_number(game)

    if game_number:
        lines.append(game_number)

    broadcasts = game.get("broadcasts") or []

    if broadcasts:
        lines.append(f"TV/Streaming: {', '.join(broadcasts)}")
    else:
        lines.append("TV/Streaming: TBA")

    status = game.get("status")

    if status:
        lines.append(f"Status: {status}")

    return "\\n".join(escape_ics(line) for line in lines)


def get_location(game):
    venue = game.get("venue") or {}

    name = venue.get("name")
    city = venue.get("city")
    state = venue.get("state")

    parts = []

    if name:
        parts.append(name)

    city_state = ", ".join(
        part for part in [city, state] if part
    )

    if city_state:
        parts.append(city_state)

    if parts:
        return ", ".join(parts)

    return "TBA"


def should_keep_game(game, now):
    start = parse_game_date(game.get("gameDate"))

    if start is None:
        return False

    end = start + GAME_DURATION

    # Keep future games plus completed/recent games for seven days
    # after their scheduled end time.
    return end + RETENTION >= now


def build_event(game, now):
    start = parse_game_date(game.get("gameDate"))

    if start is None:
        return None

    end = start + GAME_DURATION

    game_pk = game.get("gamePk")
    uid = f"yankees-playoffs-{game_pk}@mmalinconico.github.io"

    return [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{format_utc(now)}",
        f"DTSTART:{format_utc(start)}",
        f"DTEND:{format_utc(end)}",
        f"SUMMARY:{escape_ics(get_summary(game))}",
        f"LOCATION:{escape_ics(get_location(game))}",
        f"DESCRIPTION:{get_description(game)}",
        "END:VEVENT",
    ]


def main():
    if not EVENTS_FILE.exists():
        raise FileNotFoundError(
            f"{EVENTS_FILE} does not exist. Run fetch_events.py first."
        )

    data = json.loads(
        EVENTS_FILE.read_text(encoding="utf-8")
    )

    now = datetime.now(timezone.utc)

    calendar_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Matt Malinconico//Yankees Playoff Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Yankees Playoff Calendar",
        "X-WR-TIMEZONE:America/New_York",
    ]

    games = data.get("games", [])

    games.sort(
        key=lambda game: game.get("gameDate") or ""
    )

    included = 0

    for game in games:
        if not should_keep_game(game, now):
            continue

        event_lines = build_event(game, now)

        if event_lines:
            calendar_lines.extend(event_lines)
            included += 1

    calendar_lines.append("END:VCALENDAR")

    OUTPUT_FILE.write_text(
        "\r\n".join(calendar_lines) + "\r\n",
        encoding="utf-8",
    )

    print(f"Wrote {OUTPUT_FILE}")
    print(f"Included {included} postseason game(s).")


if __name__ == "__main__":
    main()
