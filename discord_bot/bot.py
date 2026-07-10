import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from object_detection.phone_detection import Detector
import asyncio


load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

detector = Detector()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready(): #runs on start
    print("Bot is online.")
    pass


@bot.command()
async def link(ctx): #generate unique token to link each discord account to user in database
    pass


@bot.command()
async def startstudy(ctx): #user starts studying, activate camera
    asyncio.get_event_loop().run_in_executor(None, detector.activate_camera)
    print("Camera activated.")
    await ctx.message.channel.send("Process started successfully! 🚀")



@bot.command()
async def endsession(ctx):
    detector.deactivate_camera()
    print("Camera deactivated.")


@bot.command()
async def mypoints(ctx):
    pass


@bot.command()
async def leaderboard(ctx):
    pass


bot.run(TOKEN)