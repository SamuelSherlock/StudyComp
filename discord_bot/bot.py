import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from requests import session
from object_detection.phone_detection import Detector
from discord_bot.stats_functions import load_stats, load_all_stats, save_stats, pause_session, load_tokens, save_tokens, finalize_session, STATS_PATH, clear_stats, load_challenges_state, save_challenges_state
from discord_bot.leaderboard_ui import build_leaderboard_embed, LeaderboardView

import asyncio
import websockets
import json
import secrets
import time


load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

detector = Detector()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

#constants
connections = {}  #list keeps track of all clients connected to the websocket server, so we can send messages to them later
token_to_user = load_tokens() #stores all discord users tokens and their corresponding discord user id, loaded from disk so tokens survive bot restarts
session_state = {} #stores the current state of each user's session
POINTS_PER_MINUTE = 2  # points awarded per minute of study time
STRIKE_PENALTY = 40  # points deducted for first strike
STRIKE_LIMIT = 3  # maximum number of strikes before penalty is applied
challenges = {
    "comp": {"message_id": None, "participants": set(), "prize": None, "stats_path": "discord_bot/comp_stats.json"},
    "casual": {"message_id": None, "participants": set(), "prize": None, "stats_path": "discord_bot/casual_stats.json"},
}
challenges, pending_setup_message_id, pending_setup_initiator_id = load_challenges_state(challenges)  # restore challenge state so it survives a bot restart


def persist_challenge_state():
    save_challenges_state(challenges, pending_setup_message_id, pending_setup_initiator_id)


def find_user_challenge_path(user_id):
    # returns the stats file for whichever active challenge this user is currently in, or None if they aren't in one
    for info in challenges.values():
        if user_id in info["participants"]:
            return info["stats_path"]
    return None


def apply_event(user_id, status):
    if user_id not in session_state:
        return  # ignore events from users who aren't in a session

    session = session_state[user_id]

    if not session["active"]:
        return  # ignore events from users who aren't actively studying

    if status == "phone" and not session["paused"]:
        session["strike_counter"] += 1  # counts toward the next penalty, resets every 3 regardless of outcome
        if session["strike_counter"] >= STRIKE_LIMIT:
            session["strike_counter"] = 0  # reset the counter, penalty group completed
            session["strikes"] += 1  # one more completed penalty group; points deducted for this in !endstudy, once real points exist
    if status == "no_person":
        print('No person detected!')  # for debugging
        pause_session(session)  # pause the session if no person is detected
    if status == "person_detected":
        print('Person detected!')  # for debugging
        pause_session(session)  # resume the session if a person is detected
           
   


    


@bot.event
async def on_ready(): #runs on start
    print("Bot is online.")
    bot.loop.create_task(start_websocket_server())
    #run web socket server in background so it can listen for connections from students' listeners
    pass

async def start_websocket_server():
    async with websockets.serve(handle_client, "0.0.0.0", 8765) as server:
        # "0.0.0.0" = accept connections from any machine, not just this one
        # 8765 = the port number students' listeners will connect to
        print("Websocket server listening on port 8765")
        await asyncio.Future()  # never completes on its own -> keeps this block open forever

# This runs once PER student who connects. "ws" is that one student's connection.
async def handle_client(ws):
    first_message = await ws.recv()   # pause here and go do other things until the client sends something
    data = json.loads(first_message) #load json data
    token = data["token"]  # extract the token from the data
    user_id = token_to_user.get(token)  # look up the user ID associated with that token
    if user_id is None: #if the token is not one we generated
        await ws.send(json.dumps({"error": "Invalid token"}))  # send an error message back to the client
        return  # stop processing this connection
    connections[user_id] = ws  # store the websocket connection in the dictionary with the user ID as the key
    session_state[user_id] = {"active": False, "points": 0, "strikes": 0}  # safe default until !startstudy actually begins a session


    try:
        while True:
            message = await ws.recv()  # wait for a message from the client
            data = json.loads(message)  # load json data
            # process incoming messages from the client
            if data.get("type") == "event":
               apply_event(user_id, data["status"])  # call a function to handle the event
    except websockets.ConnectionClosed:
        pass
    finally:
        del connections[user_id]  # remove the connection from the dictionary
        session = session_state.get(user_id)
        if session is not None and session["active"]:
            finalize_session(user_id, session, POINTS_PER_MINUTE, STRIKE_PENALTY, find_user_challenge_path(user_id))  # listener dropped mid-session, save what was earned so far
            user = bot.get_user(user_id) or await bot.fetch_user(user_id)
            await user.send(
                f"Crash detected, stats saved! Your session stats are {session['points']:.0f} points with {session['strikes']} strikes."
            )
        del session_state[user_id]  # remove the session state
        
#command to create channels and roles and then assign permissions upon setup
@bot.command()
@commands.has_permissions(administrator=True)
async def setup(ctx):
    existing = discord.utils.get(ctx.guild.categories,name="StudyComp")
    if existing is not None:
        await ctx.send("Category already exists, please delete it first then retry command.")
        return
    role_existing = discord.utils.get(ctx.guild.roles, name="Challenger")
    if role_existing is None:
        studycomp_role = await ctx.guild.create_role(name="Challenger")
    else:
        studycomp_role = role_existing
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        studycomp_role: discord.PermissionOverwrite(view_channel=True)
    }
    
    overwrites_special = {
        ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False, send_messages=False),
        studycomp_role: discord.PermissionOverwrite(view_channel=True, send_messages=False),
    }


    category = await ctx.guild.create_category("StudyComp", overwrites=overwrites)

    await ctx.guild.create_text_channel("Study-Announcements", category=category, overwrites=overwrites_special)
    await ctx.guild.create_text_channel("Leaderboard", category=category, overwrites=overwrites_special)
    await ctx.guild.create_text_channel("Study-Chat", category=category)
    await ctx.guild.create_text_channel("Study-Commands", category=category)
    await ctx.guild.create_voice_channel("Study-Voice", category=category)
    


@bot.command()
@commands.has_permissions(administrator=True)
async def startchallenge(ctx):
    global pending_setup_message_id, pending_setup_initiator_id

    if pending_setup_message_id is not None:
        await ctx.send("A challenge setup is already in progress.")
        return

    msg = await ctx.send("React with ⚔️ for a comp challenge or 🙂 for casual!")
    await msg.add_reaction("⚔️")
    await msg.add_reaction("🙂")

    pending_setup_message_id = msg.id
    pending_setup_initiator_id = ctx.author.id
    persist_challenge_state()



@bot.event
async def on_raw_reaction_add(payload):  # fires for every reaction added anywhere the bot can see
    global pending_setup_message_id, pending_setup_initiator_id

    if payload.user_id == bot.user.id:
        return  # ignore the bot's own reactions

    # --- Branch 1: reaction on the comp/casual setup prompt ---
    if payload.message_id == pending_setup_message_id:
        if payload.user_id != pending_setup_initiator_id:
            return  # only the person who ran !startchallenge can answer

        channel = bot.get_channel(payload.channel_id)

        if str(payload.emoji) == "⚔️":
            if challenges["comp"]["message_id"] is not None:
                initiator = bot.get_user(payload.user_id) or await bot.fetch_user(payload.user_id)
                await channel.send(f"{initiator.mention} a competitive challenge has been created.")
                pending_setup_message_id = None
                pending_setup_initiator_id = None
                persist_challenge_state()
                return

            await channel.send("What would you like the prize to be?")

            def check(m):
                return m.author.id == pending_setup_initiator_id and m.channel.id == payload.channel_id

            try:
                prize_message = await bot.wait_for("message", check=check, timeout=60)
            except asyncio.TimeoutError:
                await channel.send("Timed out waiting for a prize. Run !startchallenge again.")
                pending_setup_message_id = None
                pending_setup_initiator_id = None
                persist_challenge_state()
                return

            challenges["comp"]["prize"] = prize_message.content
            join_msg = await channel.send(f"🏆 Comp challenge started! Prize: {prize_message.content}. React with 👍 to join!")
            await join_msg.add_reaction("👍")
            challenges["comp"]["message_id"] = join_msg.id
            challenges["comp"]["participants"] = set()

        elif str(payload.emoji) == "🙂":
            if challenges["casual"]["message_id"] is not None:
                initiator = bot.get_user(payload.user_id) or await bot.fetch_user(payload.user_id)
                await channel.send(f"{initiator.mention} a casual challenge has already been created.")
                pending_setup_message_id = None
                pending_setup_initiator_id = None
                persist_challenge_state()
                return

            join_msg = await channel.send("Casual challenge started! React with 👍 to join!")
            await join_msg.add_reaction("👍")
            challenges["casual"]["message_id"] = join_msg.id
            challenges["casual"]["participants"] = set()

        else:
            return  # some other emoji reacted on the prompt, ignore it

        pending_setup_message_id = None
        pending_setup_initiator_id = None
        persist_challenge_state()
        return

    # --- Branch 2: reaction on one of the active challenge join messages ---
    for challenge_type, info in challenges.items():
        if payload.message_id == info["message_id"]:
            if str(payload.emoji) != "👍":
                return
            if payload.user_id in info["participants"]:
                return
            if any(payload.user_id in other["participants"] for other in challenges.values()):
                user = bot.get_user(payload.user_id) or await bot.fetch_user(payload.user_id)
                channel = bot.get_channel(payload.channel_id)
                await channel.send(f"{user.mention} you are already in an existing challenge.")
                return  # already in the other challenge, can only be in one at a time

            user = bot.get_user(payload.user_id) or await bot.fetch_user(payload.user_id)  # get_user checks cache first, fetch_user asks Discord directly

            token = secrets.token_urlsafe(16)  # generate a random token
            token_to_user[token] = user.id  # store the token and the user's Discord ID in a dictionary
            save_tokens(token_to_user)  # persist to disk so this token still works after a bot restart
            info["participants"].add(user.id)
            persist_challenge_state()

            existing_stats = load_all_stats(path=info["stats_path"])
            if user.id not in existing_stats:
                save_stats(user.id, 0, 0, path=info["stats_path"])  # seed a fresh leaderboard entry, don't overwrite existing lifetime stats

            await user.send(f"Your token is: {token}")
            return


@bot.command()
async def startstudy(ctx): #user starts studying, activate camera
    #use discord userid to retrieve the connection for that user
    user_id = ctx.message.author.id
    ws = connections.get(user_id)
    if ws is None:
        await ctx.message.channel.send("Your listener isn't connected. Make sure it's running and try again.")
        return
    session_state[user_id] = {"active": True, "start_time": time.time(), "total_absent_seconds": 0, "absent_since": None, "paused": False, "points": 0, "strikes": 0, "strike_counter": 0}
    await ws.send(json.dumps({"start": True}))  # send a message to the user's listener to start the function
    await ctx.message.channel.send("Process started successfully! 🚀")



@bot.command()
async def endstudy(ctx):
     user_id = ctx.message.author.id
     ws = connections.get(user_id)
     session = session_state.get(user_id)
     if ws is None or session is None or not session.get("active"):
         await ctx.message.channel.send("You don't have an active study session to end.")
         return
     await ws.send(json.dumps({"stop": True}))  # send a message to the user's listener to stop the function
     finalize_session(user_id, session, POINTS_PER_MINUTE, STRIKE_PENALTY, find_user_challenge_path(user_id))

     color = discord.Color.green() if session["strikes"] == 0 else discord.Color.orange()
     embed = discord.Embed(title="Study Session Ended", color=color)
     embed.add_field(name="Total Points Earned", value=f"{session['points']:.0f}")
     embed.add_field(name="Total Strikes", value=str(session['strikes']))
     await ctx.message.channel.send(embed=embed)

     session_state[user_id] = {"active": False, "points": 0, "strikes": 0}  # reset for next time


@bot.command()
async def stats(ctx, member: discord.Member = None):
    target = member or ctx.author
    lifetime = load_stats(target.id)

    embed = discord.Embed(title=f"{target.name}'s Lifetime Stats", color=discord.Color.blurple())
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="Points", value=f"{lifetime['points']:.0f}")
    embed.add_field(name="Strikes", value=str(lifetime['strikes']))

    await ctx.send(embed=embed)


@bot.command()
async def challengestats(ctx, member: discord.Member = None):
    target = member or ctx.author

    challenge_type = None
    for c_type, info in challenges.items():
        if target.id in info["participants"]:
            challenge_type = c_type
            break

    if challenge_type is None:
        await ctx.send(f"{target.mention} is not currently in a challenge.")
        return

    challenge_stats = load_stats(target.id, path=challenges[challenge_type]["stats_path"])

    embed = discord.Embed(title=f"{target.name}'s {challenge_type.capitalize()} Stats", color=discord.Color.blurple())
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="Points", value=f"{challenge_stats['points']:.0f}")
    embed.add_field(name="Strikes", value=str(challenge_stats['strikes']))

    await ctx.send(embed=embed)




async def post_leaderboard(channel, viewer_id, stats_path=STATS_PATH, title="📚 Study Leaderboard"):
    all_stats = load_all_stats(path=stats_path)
    if not all_stats:
        return False

    ranked = sorted(all_stats.items(), key=lambda entry: (-entry[1]["points"], entry[1]["strikes"]))
    view = LeaderboardView(bot, ranked, title=title)
    embed = await build_leaderboard_embed(bot, ranked, 0, viewer_id, title)
    await channel.send(embed=embed, view=view)
    return True


@bot.command()
async def leaderboard(ctx):
    #check for leaderboard channel and store in variable for later use
    leaderboard_channel = discord.utils.get(ctx.guild.channels, name="leaderboard")
    if leaderboard_channel is None:
        await ctx.send("Leaderboard channel not found.")
        return

    posted = await post_leaderboard(leaderboard_channel, ctx.author.id, title="📚 Lifetime Leaderboard")
    if not posted:
        await ctx.send("No stats available.")
        return

    #send message with link to leaderboard channel
    await ctx.send(f"{ctx.author.mention} view the updated leaderboard in {leaderboard_channel.mention}")


@bot.command()
async def challengeleaderboard(ctx, challenge_type: str):
    challenge_type = challenge_type.lower()
    if challenge_type not in challenges:
        await ctx.send("Specify either 'comp' or 'casual'.")
        return

    leaderboard_channel = discord.utils.get(ctx.guild.channels, name="leaderboard")
    if leaderboard_channel is None:
        await ctx.send("Leaderboard channel not found.")
        return

    info = challenges[challenge_type]
    posted = await post_leaderboard(leaderboard_channel, ctx.author.id, info["stats_path"], title=f"{challenge_type.capitalize()} Leaderboard")
    if not posted:
        await ctx.send(f"No stats available for the {challenge_type} challenge.")
        return

    await ctx.send(f"{ctx.author.mention} view the updated leaderboard in {leaderboard_channel.mention}")



@bot.command()
async def pause(ctx):
    current_time = time.strftime("%I:%M %p")
    session = session_state.get(ctx.author.id)

    if  session is None or not session["active"]:
        await ctx.send("You don't have an active study session to pause.")
        return
    if not session["paused"]:
        await ctx.send(f"Session paused at {current_time}. Resume session by typing !pause again.")
        session["paused"] = True
    else:
        await ctx.send(f"Session resumed at {current_time}.")
        session["paused"] = False

    pause_session(session)


@bot.command()
@commands.has_permissions(administrator=True)
async def endchallenge(ctx, challenge_type: str):
    challenge_type = challenge_type.lower()
    if challenge_type not in challenges:
        await ctx.send("Specify either 'comp' or 'casual'.")
        return

    info = challenges[challenge_type]
    if info["message_id"] is None:
        await ctx.send(f"There's no active {challenge_type} challenge to end.")
        return

    announcements_channel = discord.utils.get(ctx.guild.channels, name="study-announcements")
    if announcements_channel is None:
        await ctx.send("Study-Announcements channel not found.")
        return

    all_stats = load_all_stats(path=info["stats_path"])
    await post_leaderboard(announcements_channel, ctx.author.id, info["stats_path"], title=f"{challenge_type.capitalize()} Leaderboard - Final Results")

    ranked = sorted(all_stats.items(), key=lambda entry: (-entry[1]["points"], entry[1]["strikes"]))
    if ranked:
        winner_id = ranked[0][0]
        winner = bot.get_user(winner_id) or await bot.fetch_user(winner_id)
        if challenge_type == "comp":
            await announcements_channel.send(f"🎉 Congrats {winner.mention}, you won the comp challenge! Prize: {info['prize']}")
        else:
            await announcements_channel.send(f"🎉 Congrats {winner.mention}, you won the casual challenge!")
    else:
        await announcements_channel.send(f"The {challenge_type} challenge ended with no participants.")

    clear_stats(info["stats_path"])
    info["message_id"] = None
    info["participants"] = set()
    info["prize"] = None
    persist_challenge_state()


bot.run(TOKEN)
