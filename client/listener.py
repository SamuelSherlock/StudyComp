import asyncio       # lets us write pausable/waitable code
import websockets     # the library for connecting to a websocket server
import json
import sys   # lets us find the exact python interpreter currently running this script
import os    # lets us build a file path that works regardless of where you run this from
from dotenv import load_dotenv


ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")  # always client/.env, no matter where this is run from

load_dotenv(ENV_PATH)
token = os.getenv("STUDY_TOKEN")  # get the token from the .env files
if token is None:
    token = input("Paste your study token here: ")
    with open(ENV_PATH, "w") as f:
        f.write(f"STUDY_TOKEN={token}\n")



async def read_detector_output(process, ws): #process parameter is reference to background phone_detection.py running
   while True:
      line = await process.stdout.readline()  # pause here until the detector outputs a line
      if not line:  # if the detector has stopped running, exit this loop
         break
      decoded = line.decode().strip()
      data = json.loads(decoded)  # turn the line into a python dictionary

      if data.get("status") == "phone":
         print("Phone detected! Strike added.")  

      await ws.send(json.dumps({"type": "event", "status": data["status"]}))   
        
   

async def main():
    # Knock on the door your bot opened - same host+port it's listening on
    async with websockets.connect("ws://localhost:8765") as ws:
        print("Connected to the bot's websocket server!")
        await ws.send(json.dumps({"token": token}))  # send a message to the bot
        process = None #declare outside of if statements so we can use it later to stop program

        async for message in ws: #iterate over the connection, pausing here until the bot sends a message back
         data = json.loads(message) #turn text into python dictionary
         if data.get("error"):
            print(f"Server error: {data['error']}")
            break
         if data.get("start"):
          process = await asyncio.create_subprocess_exec(sys.executable, "-m", "object_detection.phone_detection", stdout=asyncio.subprocess.PIPE,) #outputs are now piped to this program so we can read them and send them to the bot
          #runs detector as seperate background program so it can run while we listen for messages from the bot
          asyncio.create_task(read_detector_output(process, ws))  # start reading the detector's output in the background
          print("Starting the function now!")
         elif data.get("stop"):
          if process is not None:
                try:
                    process.terminate()
                    print("Stopping the function now!")
                except ProcessLookupError:
                    print("Process had already stopped on its own.")




asyncio.run(main())   # actually starts the async engine and runs main()