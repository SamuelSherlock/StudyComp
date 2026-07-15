import asyncio       # lets us write pausable/waitable code
import websockets     # the library for connecting to a websocket server
import json
import sys   # lets us find the exact python interpreter currently running this script
import os    # lets us build a file path that works regardless of where you run this from
from dotenv import load_dotenv


load_dotenv()
token = os.getenv("STUDY_TOKEM")  # get the token from the .env files
if token is None:
    token = input("Paste your study token here: ")
    with open(".env", "w") as f:
        f.write(f"STUDY_TOKEN={token}\n")

async def main():
    # Knock on the door your bot opened - same host+port it's listening on
    async with websockets.connect("ws://localhost:8765") as ws:
        print("Connected to the bot's websocket server!")
        await ws.send(json.dumps({"token": os.getenv("STUDY_TOKEN")}))  # send a message to the bot

        process = None #declare outside of if statements so we can use it later to stop program

        async for message in ws: #iterate over the connection, pausing here until the bot sends a message back
         data = json.loads(message) #turn text into python dictionary
         if data.get("start"):
          process = await asyncio.create_subprocess_exec(sys.executable, "-m", "object_detection.phone_detection")
          #runs detector as seperate background program so it can run while we listen for messages from the bot
          print("Starting the function now!")
         elif data.get("stop"):
          if process is not None:
                try:
                    process.terminate()
                    print("Stopping the function now!")
                except ProcessLookupError:
                    print("Process had already stopped on its own.")




asyncio.run(main())   # actually starts the async engine and runs main()