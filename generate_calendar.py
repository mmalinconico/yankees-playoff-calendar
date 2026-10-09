import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


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


EASTERN = ZoneInfo("America/New_York")


def get_official_game_date(game):
    """Use MLB's calendar date for an all-day TBD event."""
    official = game.get("officialDate")
    if official:
        try:
            return date.fromisoformat(official)
        except ValueError:
            pass

    start = parse_game_date(game.get("gameDate"))
    if start is None:
        return None

    return start.astimezone(EASTERN).date()


def is_placeholder_time(game):
    """Prefer MLB's explicit flag; recognize its observed fallback."""
    if is_final_game(game):
        return False

    time_tbd = game.get("startTimeTBD")
    if time_tbd is True:
        return True
    if time_tbd is False:
        return False

    start = parse_game_date(game.get("gameDate"))
    # Legacy MLB postseason placeholder: 07:33 UTC.
    # Do not classify every legitimate :33 first pitch as TBD.
    return bool(
        start
        and start.hour == 7
        and start.minute == 33
        and start.second == 0
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
        official_day = get_official_game_date(game)
        if official_day is None:
            return False
        return official_day >= (
            now.astimezone(EASTERN) - RETENTION
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
        event_date = get_official_game_date(game)

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


def fold_ics_line(line):
    """Fold content at 75 UTF-8 octets per RFC 5545."""
    folded = []
    segment = ""
    octets = 0

    for char in line:
        size = len(char.encode("utf-8"))
        if segment and octets + size > 75:
            folded.append(segment)
            segment = " " + char
            octets = 1 + size
        else:
            segment += char
            octets += size

    folded.append(segment)
    return folded


def unfold_ics_lines(content):
    """Restore logical lines, including previously folded ICS files."""
    lines = []
    for line in content.splitlines():
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    return lines


def read_existing_event_versions():
    """Look up previous stamps and content by stable event UID."""
    if not OUTPUT_FILE.exists():
        return {}

    existing = {}
    current = None
    for line in unfold_ics_lines(
        OUTPUT_FILE.read_text(encoding="utf-8")
    ):
        if line == "BEGIN:VEVENT":
            current = [line]
        elif current is not None:
            current.append(line)
            if line == "END:VEVENT":
                uid = next(
                    (x[4:] for x in current if x.startswith("UID:")),
                    None,
                )
                stamp = next(
                    (x for x in current if x.startswith("DTSTAMP:")),
                    None,
                )
                if uid and stamp:
                    content = tuple(
                        x for x in current
                        if not x.startswith("DTSTAMP:")
                    )
                    existing[uid] = (stamp, content)
                current = None

    return existing


def preserve_unchanged_timestamp(event_lines, existing):
    """Do not revise a calendar event whose details are unchanged."""
    uid = next(
        (x[4:] for x in event_lines if x.startswith("UID:")),
        None,
    )
    prior = existing.get(uid)
    if prior:
        stamp, content = prior
        without_stamp = tuple(
            x for x in event_lines
            if not x.startswith("DTSTAMP:")
        )
        if without_stamp == content:
            for index, line in enumerate(event_lines):
                if line.startswith("DTSTAMP:"):
                    event_lines[index] = stamp
                    break

    return event_lines


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
    existing_versions = read_existing_event_versions()

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
            event_lines = preserve_unchanged_timestamp(
                event_lines,
                existing_versions,
            )
            calendar_lines.extend(
                event_lines
            )
            included += 1

    calendar_lines.append(
        "END:VCALENDAR"
    )

    folded_lines = []
    for line in calendar_lines:
        folded_lines.extend(fold_ics_line(line))

    content = ("\r\n".join(folded_lines) + "\r\n").encode("utf-8")
    if OUTPUT_FILE.exists() and OUTPUT_FILE.read_bytes() == content:
        print(f"No calendar changes in {OUTPUT_FILE}")
        return

    OUTPUT_FILE.write_bytes(content)

    print(f"Wrote {OUTPUT_FILE}")
    print(
        f"Included {included} "
        "postseason game(s)."
    )


if __name__ == "__main__":
    main()