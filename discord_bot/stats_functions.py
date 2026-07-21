#file for helper functions with the discord bot and stats/database

import os
import json
import time

STATS_PATH = "discord_bot/lifetime_stats.json"
TOKENS_PATH = "discord_bot/study_tokens.json"


def load_tokens():
    if os.path.exists(TOKENS_PATH):
        with open(TOKENS_PATH, "r") as f:
            return json.load(f)  # {token: user_id}
    return {}


def save_tokens(token_to_user):
    with open(TOKENS_PATH, "w") as f:
        json.dump(token_to_user, f)


def load_stats(user_id, ):
    if os.path.exists(STATS_PATH):
        with open(STATS_PATH, "r") as f:
            stats = json.load(f)
            return stats.get(str(user_id), {"points": 0, "strikes": 0})
    return {"points": 0, "strikes": 0}

def load_all_stats():
    if os.path.exists(STATS_PATH):
        with open(STATS_PATH, "r") as f:
            all_stats = json.load(f)
            return {int(user_id): stats for user_id, stats in all_stats.items()}
    return {}


def save_stats(user_id, points, strikes):
    # Save the user's stats to a file or database
    if os.path.exists(STATS_PATH):
        with open(STATS_PATH, "r") as f:
            stats = json.load(f)
    else:
        stats = {}

    stats[str(user_id)] = {"points": points, "strikes": strikes}  # keys must be strings to match what json.load gives back

    with open(STATS_PATH, "w") as f:
        json.dump(stats, f)

def pause_session(session):
    if session["absent_since"] is None:
      session["absent_since"] = time.time()  # mark the time when the user was first detected as absent
    else:
      session["total_absent_seconds"] += time.time() - session["absent_since"] #add current time since absent to total
      session["absent_since"] = None

def finalize_session(user_id, session, points_per_minute, strike_penalty):
    # closes out an active session and folds its points/strikes into the lifetime totals on disk
    if session["absent_since"] is not None:
        pause_session(session)  # close out any open pause/absence window so it counts against study time
    time_passed = (time.time() - session["start_time"]) - session["total_absent_seconds"]  # total time spent studying, minus any time the user was absent
    session["points"] += (time_passed / 60) * points_per_minute  # add points for the time spent studying
    session["points"] = max(0, session["points"] - (session["strikes"] * strike_penalty))  # deduct for each completed penalty group, now that real points exist
    lifetime = load_stats(user_id)  # read this user's current lifetime totals from disk
    new_points = lifetime["points"] + session["points"]  # fold this session's totals into the lifetime totals
    new_strikes = lifetime["strikes"] + session["strikes"]
    save_stats(user_id, new_points, new_strikes)  # persist the updated lifetime totals back to disk
