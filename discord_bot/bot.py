import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from requests import session
from object_detection.phone_detection import Detector
from discord_bot.stats_functions import load_stats, load_all_stats, pause_session, load_tokens, save_tokens, finalize_session
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
challenge_message_id = None  # id of the active challenge signup message, or None if no challenge is open
challenge_participants = set()  # discord user ids who have already been given a token for the current challenge

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
            finalize_session(user_id, session, POINTS_PER_MINUTE, STRIKE_PENALTY)  # listener dropped mid-session, save what was earned so far
            user = bot.get_user(user_id) or await bot.fetch_user(user_id)
            await user.send(
                f"Crash detected, stats saved! Your session stats are {session['points']:.0f} points with {session['strikes']} strikes."
            )
        del session_state[user_id]  # remove the session state
        
#command to create channels and roles and then assign permissions upon setup
@commands.has_permissions(administrator=True)
@bot.command()
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
async def startchallenge(ctx):  # post a signup message - anyone who reacts with 👍 gets a token
    global challenge_message_id
    msg = await ctx.send("React with 👍 to join the challenge!")
    await msg.add_reaction("👍")  # bot adds the reaction itself so users just have to click it
    challenge_message_id = msg.id  # remember which message's reactions count for this challenge
    challenge_participants.clear()  # fresh signup list for this new challenge


@bot.event
async def on_raw_reaction_add(payload):  # fires for every reaction added anywhere the bot can see
    if payload.message_id != challenge_message_id:
        return  # not a reaction on the current challenge message
    if str(payload.emoji) != "👍":
        return  # wrong emoji
    if payload.user_id == bot.user.id:
        return  # ignore the bot's own reaction added in !startchallenge
    if payload.user_id in challenge_participants:
        return  # this user already got a token for this challenge

    user = bot.get_user(payload.user_id) or await bot.fetch_user(payload.user_id)  # get_user checks cache first, fetch_user asks Discord directly

    token = secrets.token_urlsafe(16)  # generate a random token
    token_to_user[token] = user.id  # store the token and the user's Discord ID in a dictionary
    save_tokens(token_to_user)  # persist to disk so this token still works after a bot restart
    challenge_participants.add(user.id)
    await user.send(f"Your token is: {token}")


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
     finalize_session(user_id, session, POINTS_PER_MINUTE, STRIKE_PENALTY)

     await ctx.message.channel.send(
         f"Session complete! You earned {session['points']:.0f} points with {session['strikes']} strikes this session."
     )

     session_state[user_id] = {"active": False, "points": 0, "strikes": 0}  # reset for next time


@bot.command()
async def stats(ctx, member: discord.Member = None):
    target = member or ctx.author
    lifetime = load_stats(target.id)
    await ctx.send(f"{target.mention} has {lifetime['points']:.0f} points and {lifetime['strikes']} strikes.")



@bot.command()
async def leaderboard(ctx):
    all_stats = load_all_stats()
    if not all_stats:
        await ctx.send("No stats available.")
        return

    # Sort by points descending, strikes ascending as tiebreaker
    ranked = sorted(all_stats.items(), key=lambda entry: (-entry[1]["points"], entry[1]["strikes"]))

    lines = ["Leaderboard:"]
    for rank, (user_id, stats_data) in enumerate(ranked, start=1):
        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
        lines.append(f"{rank}. {user.name}: {stats_data['points']:.0f} points, {stats_data['strikes']} strikes")

    await ctx.send("\n".join(lines))


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


bot.run(TOKEN)