import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from object_detection.phone_detection import Detector
from discord_bot.stats_functions import save_stats, load_stats, load_all_stats
import asyncio
import websockets
import json
import secrets


load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

detector = Detector()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

#constants
connections = {}  #list keeps track of all clients connected to the websocket server, so we can send messages to them later
token_to_user = {} #stores all discord users tokens and their corresponding discord user id, so we can link them to the database later
session_state = {} #stores the current state of each user's session
POINTS_PER_MINUTE = 2  # points awarded per minute of study time
STRIKE_PENALTY = 40  # points deducted for first strike
STRIKE_LIMIT = 3  # maximum number of strikes before penalty is applied
challenge_message_id = None  # id of the active challenge signup message, or None if no challenge is open
challenge_participants = set()  # discord user ids who have already been given a token for the current challenge



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
    except websockets.ConnectionClosed:
        pass
    finally:
        del connections[user_id]  # remove the connection from the dictionary
        del session_state[user_id]  # remove the session state
        

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
    challenge_participants.add(user.id)
    await user.send(f"Your token is: {token}")


@bot.command()
async def startstudy(ctx): #user starts studying, activate camera
    #use discord userid to retrieve the connection for that user
    user_id = ctx.message.author.id
    ws = connections[user_id]
    session_state[user_id] = {"active": True, "points": 0, "strikes": 0}  # this is the real start of a session, not the start of the websocket connection
    await ws.send(json.dumps({"start": True}))  # send a message to the user's listener to start the function
    await ctx.message.channel.send("Process started successfully! 🚀")



@bot.command()
async def endsession(ctx):
     user_id = ctx.message.author.id
     ws = connections[user_id]
     await ws.send(json.dumps({"stop": True}))  # send a message to the user's listener to stop the function

     session = session_state[user_id]
     lifetime = load_stats(user_id)  # read this user's current lifetime totals from disk
     new_points = lifetime["points"] + session["points"]  # fold this session's totals into the lifetime totals
     new_strikes = lifetime["strikes"] + session["strikes"]
     save_stats(user_id, new_points, new_strikes)  # persist the updated lifetime totals back to disk

     await ctx.message.channel.send(
         f"Session complete! You earned {session['points']} points with {session['strikes']} strikes this session."
     )

     session_state[user_id] = {"active": False, "points": 0, "strikes": 0}  # reset for next time


@bot.command()
async def stats(ctx, member: discord.Member = None):
    target = member or ctx.author
    lifetime = load_stats(target.id)
    await ctx.send(f"{target.mention} has {lifetime['points']} points and {lifetime['strikes']} strikes.")



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
        lines.append(f"{rank}. {user.name}: {stats_data['points']} points, {stats_data['strikes']} strikes")

    await ctx.send("\n".join(lines))


bot.run(TOKEN)