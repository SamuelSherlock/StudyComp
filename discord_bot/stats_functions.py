#file for helper functions with the discord bot and stats/database

import os
import json

STATS_PATH = "discord_bot/lifetime_stats.json"


def load_stats(user_id):
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
