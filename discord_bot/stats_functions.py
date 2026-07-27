#file for helper functions with the discord bot and stats/database

import os
import json
import time

STATS_PATH = "discord_bot/lifetime_stats.json"
TOKENS_PATH = "discord_bot/study_tokens.json"
CHALLENGES_PATH = "discord_bot/challenges_state.json"


def load_tokens():
    if os.path.exists(TOKENS_PATH):
        with open(TOKENS_PATH, "r") as f:
            return json.load(f)  # {token: user_id}
    return {}


def save_tokens(token_to_user):
    with open(TOKENS_PATH, "w") as f:
        json.dump(token_to_user, f)


def load_stats(user_id, path=STATS_PATH):
    if os.path.exists(path):
        with open(path, "r") as f:
            stats = json.load(f)
            return stats.get(str(user_id), {"points": 0, "strikes": 0})
    return {"points": 0, "strikes": 0}

def load_all_stats(path=STATS_PATH):
    if os.path.exists(path):
        with open(path, "r") as f:
            all_stats = json.load(f)
            return {int(user_id): stats for user_id, stats in all_stats.items()}
    return {}


def save_stats(user_id, points, strikes, path=STATS_PATH):
    # Save the user's stats to a file or database
    if os.path.exists(path):
        with open(path, "r") as f:
            stats = json.load(f)
    else:
        stats = {}

    stats[str(user_id)] = {"points": points, "strikes": strikes}  # keys must be strings to match what json.load gives back

    with open(path, "w") as f:
        json.dump(stats, f)

def pause_session(session):
    if session["absent_since"] is None:
      session["absent_since"] = time.time()  # mark the time when the user was first detected as absent
    else:
      session["total_absent_seconds"] += time.time() - session["absent_since"] #add current time since absent to total
      session["absent_since"] = None

def finalize_session(user_id, session, points_per_minute, strike_penalty, extra_path=None):
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

    if extra_path is not None:
        # also credit this session to whichever active challenge the user is currently in, if any
        extra = load_stats(user_id, path=extra_path)
        save_stats(user_id, extra["points"] + session["points"], extra["strikes"] + session["strikes"], path=extra_path)

def clear_stats(path):
    with open(path, "w") as f:
        json.dump({}, f)


def load_challenges_state(challenges):
    # fills in the given challenges dict (and pending setup) from disk, if a save exists
    if not os.path.exists(CHALLENGES_PATH):
        return challenges, None, None

    with open(CHALLENGES_PATH, "r") as f:
        data = json.load(f)

    for challenge_type, info in data.get("challenges", {}).items():
        if challenge_type in challenges:
            challenges[challenge_type]["message_id"] = info.get("message_id")
            challenges[challenge_type]["participants"] = set(info.get("participants", []))  # JSON has no set type, stored as a list
            challenges[challenge_type]["prize"] = info.get("prize")

    return challenges, data.get("pending_setup_message_id"), data.get("pending_setup_initiator_id")


def save_challenges_state(challenges, pending_setup_message_id, pending_setup_initiator_id):
    data = {
        "challenges": {
            challenge_type: {
                "message_id": info["message_id"],
                "participants": list(info["participants"]),  # sets aren't JSON-serializable, convert to a list
                "prize": info["prize"],
            }
            for challenge_type, info in challenges.items()
        },
        "pending_setup_message_id": pending_setup_message_id,
        "pending_setup_initiator_id": pending_setup_initiator_id,
    }
    with open(CHALLENGES_PATH, "w") as f:
        json.dump(data, f)