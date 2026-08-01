"""ICT kill-zone timing edge - bounded, transparent confidence adjustment.

Research + this platform's own trade data agree: setups in the London kill zone
(07:00-10:00 UTC, which forms the day's high/low ~70% of the time) and the New
York / London-NY overlap (12:00-15:00 UTC, the highest-volume window) are
higher-probability, while the Asian dead tape (00:00-06:00 UTC) is the weakest.
This nudges confidence by a small, capped amount based on WHEN the setup forms.
Pure function of UTC time - no network, fully testable, easy to audit.
"""
from datetime import datetime, timezone

# hour (UTC) -> (label, points). Points are intentionally small: timing is a
# prior, not a thesis. Bounded to +/-4.
KILLZONE_PTS = 4
SESSION_PTS = 1
ASIAN_PTS = -3


def zone(hour):
    if 7 <= hour < 10:
        return "London kill zone", KILLZONE_PTS
    if 12 <= hour < 15:
        return "New York kill zone (London overlap)", KILLZONE_PTS
    if 10 <= hour < 12 or 15 <= hour < 16:
        return "active session (post kill zone)", SESSION_PTS
    if 0 <= hour < 6:
        return "Asian session (low volatility)", ASIAN_PTS
    return "off-hours (thin liquidity)", 0


def adjustment(now=None):
    """Return (delta_points, rationale) from the current UTC hour."""
    now = now or datetime.now(timezone.utc)
    label, pts = zone(now.hour)
    sign = "+" if pts >= 0 else ""
    return pts, f"{label} ({sign}{pts})"
