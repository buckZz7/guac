#!/usr/bin/env python3
"""guac daily delivery — emits the day's human-facing sponsorship.

Used as the companion surface: run it once a day to produce the "brought to
you by" message for a user, and deliver it (e.g. via a no_agent Hermes cron
job to Telegram). Zero LLM tokens by design.

Usage:
    python daily.py [--email bob@x.com] [--ads-per-day 1]
    -> prints the sponsorship message(s), or nothing if none due today
"""
import argparse
import datetime as _dt
import json
import sys

import config
import portal


def _today():
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")


def _state():
    if not config.STATE_FILE.exists():
        return {}
    try:
        return json.loads(config.STATE_FILE.read_text())
    except Exception:
        return {}


def _active_offers():
    """Active portal offers (not paused, budget remaining), falling back to the
    static ads.json if no portal offers are configured. Matches the gateway."""
    portal_offers = [o for o in portal._offers()
                     if o["active"] and not o["paused"]
                     and o.get("spent", 0) < o.get("budget", 0)]
    if portal_offers:
        return portal_offers
    return config.load_ads()


def _sponsor_label(ad):
    return ad.get("advertiser") or ad.get("sponsor") or "Sponsor"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", default="")
    ap.add_argument("--ads-per-day", type=int, default=1)
    args = ap.parse_args()

    ads = _active_offers()
    if not ads:
        print("(no sponsorships configured)")
        return

    # Deterministic pick: rotate by day so the same sponsor isn't shown daily.
    day_offset = _dt.date.today().toordinal()
    # Pick up to ads_per_day offers, rotating daily.
    picks = []
    for i in range(args.ads_per_day):
        picks.append(ads[(day_offset + i) % len(ads)])

    for ad in picks:
        print(f"✨ Brought to you by {_sponsor_label(ad)} — {ad.get('headline', '')}.")
        if ad.get("claim"):
            print(f"   Redeem: {ad['claim']}")
        if ad.get("body"):
            print(f"   {ad['body']}")
        print()


if __name__ == "__main__":
    main()
