# Yankees Playoff Calendar

Automatically updated calendar for New York Yankees postseason games.

## Calendar Subscription

Subscribe using:

https://mmalinconico.github.io/yankees-playoff-calendar/yankees-playoffs.ics

## Included Information

Each Yankees postseason game includes:

- Date and scheduled first-pitch time
- 3-hour event duration
- Opponent
- Postseason series
- Game number and series length
- Stadium, city, and state
- TV/streaming information
- Current game status

## If Necessary Games

Potential elimination-series games are automatically labeled **(If Necessary)** when they are not yet guaranteed to be played.

As a series progresses:

- The label is removed when a game becomes mathematically necessary.
- Unplayed games are removed if the series is clinched before they are needed.
- Existing calendar events retain stable IDs so updates modify the same event rather than creating duplicates.

## Updates

The calendar checks for updates every 4 hours from **September 20 through November 10** each year.

It automatically reflects changes to:

- Game dates and times
- Opponents
- Venues
- Series status
- TV/streaming assignments
- If-necessary status

Completed games remain on the calendar for approximately **7 days** before being removed.

## Data

Schedule and game information is retrieved from MLB's public Stats API.

The calendar is generated automatically using GitHub Actions and published through GitHub Pages.
