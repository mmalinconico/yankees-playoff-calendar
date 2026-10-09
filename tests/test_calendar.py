import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import generate_calendar as cal
import fetch_events as fetch


def game(number, total=3, winner=None, game_type="F", tbd=False, game_date=None):
    if game_date is None:
        game_date = f"2099-10-{number:02d}T23:00:00Z"
    return {
        "gamePk": 990000 + (100 * total) + number,
        "gameDate": game_date,
        "officialDate": f"2099-10-{number:02d}",
        "startTimeTBD": tbd,
        "status": "Final" if winner else "Scheduled",
        "statusAbstract": "Final" if winner else "Preview",
        "gameType": game_type,
        "seriesDescription": "AL Division Series" if total == 5 else "AL Wild Card Series",
        "seriesGameNumber": number,
        "gamesInSeries": total,
        "homeTeam": "New York Yankees",
        "awayTeam": "Boston Red Sox",
        "opponent": "Boston Red Sox",
        "yankeesHome": True,
        "homeWinner": winner == "yankees" if winner else None,
        "awayWinner": winner == "opponent" if winner else None,
        "homeScore": 5 if winner == "yankees" else 1 if winner else None,
        "awayScore": 5 if winner == "opponent" else 1 if winner else None,
        "venue": {"name": "Yankee Stadium", "city": "Bronx", "state": "NY"},
        "broadcasts": ["FOX"],
    }


class SeriesTests(unittest.TestCase):
    def state(self, games):
        return cal.build_series_states(games)[cal.get_series_key(games[0])]

    def test_wildcard_initial_game_three_is_conditional(self):
        games = [game(n) for n in (1, 2, 3)]
        state = self.state(games)
        self.assertFalse(cal.game_is_if_necessary(games[0], state))
        self.assertFalse(cal.game_is_if_necessary(games[1], state))
        self.assertTrue(cal.game_is_if_necessary(games[2], state))

    def test_wildcard_tied_series_makes_game_three_necessary(self):
        games = [game(1, winner="yankees"), game(2, winner="opponent"), game(3)]
        state = self.state(games)
        self.assertFalse(cal.series_is_clinched(state))
        self.assertFalse(cal.game_is_if_necessary(games[2], state))

    def test_wildcard_sweep_removes_unplayed_game_three(self):
        games = [game(1, winner="yankees"), game(2, winner="yankees"), game(3)]
        state = self.state(games)
        self.assertTrue(cal.series_is_clinched(state))
        now = datetime(2099, 9, 29, tzinfo=timezone.utc)
        self.assertFalse(cal.should_keep_game(games[2], now, state))
        self.assertTrue(cal.should_keep_game(games[1], now, state))

    def test_best_of_five_game_four_becomes_required(self):
        games = [game(n, total=5, game_type="D") for n in range(1, 6)]
        self.assertFalse(cal.game_is_if_necessary(games[2], self.state(games)))
        self.assertTrue(cal.game_is_if_necessary(games[3], self.state(games)))
        self.assertTrue(cal.game_is_if_necessary(games[4], self.state(games)))
        games[0] = game(1, total=5, winner="yankees", game_type="D")
        games[1] = game(2, total=5, winner="opponent", game_type="D")
        state = self.state(games)
        self.assertFalse(cal.game_is_if_necessary(games[3], state))
        self.assertTrue(cal.game_is_if_necessary(games[4], state))

    def test_away_at_home_is_independent_of_venue(self):
        unusual = game(1)
        unusual["awayTeam"] = "New York Yankees"
        unusual["homeTeam"] = "Tampa Bay Rays"
        unusual["venue"] = {"name": "Yankee Stadium", "city": "Bronx", "state": "NY"}
        self.assertEqual(cal.get_matchup(unusual), "New York Yankees @ Tampa Bay Rays")
        self.assertEqual(cal.get_location(unusual), "Yankee Stadium, Bronx, NY")


class TbdTests(unittest.TestCase):
    def test_explicit_tbd_and_official_date(self):
        g = game(3, tbd=True, game_date="2099-10-04T07:33:00Z")
        self.assertTrue(cal.is_placeholder_time(g))
        self.assertEqual(cal.get_official_game_date(g).isoformat(), "2099-10-03")
        event = cal.build_event(g, datetime.now(timezone.utc))
        self.assertIn("DTSTART;VALUE=DATE:20991003", event)
        self.assertIn("DTEND;VALUE=DATE:20991004", event)
        self.assertIn("TBD", next(x for x in event if x.startswith("SUMMARY:")))

    def test_explicit_real_time_is_not_tbd(self):
        g = game(3, tbd=False, game_date="2099-10-04T07:33:00Z")
        self.assertFalse(cal.is_placeholder_time(g))
        event = cal.build_event(g, datetime.now(timezone.utc))
        self.assertIn("DTSTART:20991004T073300Z", event)

    def test_legacy_placeholder_is_recognized_narrowly(self):
        g = game(3, tbd=None, game_date="2099-10-04T07:33:00Z")
        self.assertTrue(cal.is_placeholder_time(g))
        g["gameDate"] = "2099-10-04T19:33:00Z"
        self.assertFalse(cal.is_placeholder_time(g))

    def test_fetcher_preserves_mlb_tbd_and_official_date(self):
        raw = {
            "gamePk": 8,
            "gameDate": "2099-10-04T07:33:00Z",
            "officialDate": "2099-10-03",
            "status": {"detailedState": "Scheduled", "startTimeTBD": True},
            "teams": {
                "away": {"team": {"name": "Boston Red Sox", "id": 111}},
                "home": {"team": {"name": "New York Yankees", "id": 147}},
            },
            "venue": {"id": 1, "name": "Neutral Park"},
        }
        with patch.object(fetch, "fetch_venue", return_value={"name": "Neutral Park"}):
            normalized = fetch.normalize_game(raw, {})
        self.assertTrue(normalized["startTimeTBD"])
        self.assertEqual(normalized["officialDate"], "2099-10-03")


class IcsTests(unittest.TestCase):
    def test_folding_respects_octets_and_unfolds_without_loss(self):
        line = "SUMMARY:" + ("Tampa Bay Rays @ New York Yankees — " * 8)
        folded = cal.fold_ics_line(line)
        self.assertGreater(len(folded), 1)
        self.assertTrue(all(len(part.encode("utf-8")) <= 75 for part in folded))
        self.assertEqual(cal.unfold_ics_lines("\r\n".join(folded)), [line])

    def test_unchanged_generation_preserves_exact_bytes_and_timestamp(self):
        with tempfile.TemporaryDirectory() as folder:
            original_events = cal.EVENTS_FILE
            original_output = cal.OUTPUT_FILE
            cal.EVENTS_FILE = Path(folder) / "events.json"
            cal.OUTPUT_FILE = Path(folder) / "calendar.ics"
            try:
                cal.EVENTS_FILE.write_text(
                    json.dumps({"games": [game(1), game(2), game(3)]}),
                    encoding="utf-8",
                )
                with contextlib.redirect_stdout(io.StringIO()):
                    cal.main()
                first = cal.OUTPUT_FILE.read_bytes()
                self.assertIn(b"UID:yankees-playoffs-", first)
                with contextlib.redirect_stdout(io.StringIO()):
                    cal.main()
                self.assertEqual(first, cal.OUTPUT_FILE.read_bytes())
                self.assertTrue(all(
                    len(line) <= 75
                    for line in first.split(b"\r\n") if line
                ))
            finally:
                cal.EVENTS_FILE = original_events
                cal.OUTPUT_FILE = original_output

    def test_changed_game_updates_calendar_but_keeps_uid(self):
        with tempfile.TemporaryDirectory() as folder:
            prior_events = cal.EVENTS_FILE
            prior_output = cal.OUTPUT_FILE
            cal.EVENTS_FILE = Path(folder) / "events.json"
            cal.OUTPUT_FILE = Path(folder) / "calendar.ics"
            try:
                fixture = game(2)
                cal.EVENTS_FILE.write_text(json.dumps({"games": [fixture]}))
                with contextlib.redirect_stdout(io.StringIO()):
                    cal.main()
                original = cal.OUTPUT_FILE.read_text()
                fixture["broadcasts"] = ["ESPN"]
                cal.EVENTS_FILE.write_text(json.dumps({"games": [fixture]}))
                with contextlib.redirect_stdout(io.StringIO()):
                    cal.main()
                updated = cal.OUTPUT_FILE.read_text()
                self.assertNotEqual(original, updated)
                self.assertIn("TV/Streaming: ESPN", updated)
                self.assertIn(
                    f"UID:yankees-playoffs-{fixture['gamePk']}@mmalinconico.github.io",
                    updated,
                )
            finally:
                cal.EVENTS_FILE = prior_events
                cal.OUTPUT_FILE = prior_output


if __name__ == "__main__":
    unittest.main()
