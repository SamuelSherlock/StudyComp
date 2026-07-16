import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from object_detection.phone_detection import Detector
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

connections = {}  #list keeps track of all clients connected to the websocket server, so we can send messages to them later
token_to_user = {} #stores all discord users tokens and their corresponding discord user id, so we can link them to the database later
session_state = {} #stores the current state of each user's session
user_stats = {} #individual user statistics
POINTS_PER_MINUTE = 2  # points awarded per minute of study time
STRIKE_PENALTY = 40  # points deducted for first strike
STRIKE_LIMIT = 3  # maximum number of strikes before penalty is applied



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
    session_state[user_id] = "idle"  # set the initial session state
    user_stats.setdefault(user_id, {"points": 0, "strikes": 0})  # only initialize lifetime stats the first time we ever see this user

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
async def link(ctx): #generate unique token to link each discord account to user in database
    token = secrets.token_urlsafe(16)          # generate a random token
    token_to_user[token] = ctx.author.id  # store the token and the user's Discord ID in a dictionary
    await ctx.author.send(f"Your token is: {token}")

    pass


@bot.command()
async def startstudy(ctx): #user starts studying, activate camera
    #use discord userid to retrieve the connection for that user
    ws = connections[ctx.message.author.id]
    await ws.send(json.dumps({"start": True}))  # send a message to the user's listener to start the function
    await ctx.message.channel.send("Process started successfully! 🚀")



@bot.command()
async def endsession(ctx):
     ws = connections[ctx.message.author.id]
     await ws.send(json.dumps({"stop": True}))  # send a message to the user's listener to stop the function
     await ctx.message.channel.send("Process ended successfully! 🚀")


@bot.command()
async def mypoints(ctx):
    pass


@bot.command()
async def leaderboard(ctx):
    pass


bot.run(TOKEN)