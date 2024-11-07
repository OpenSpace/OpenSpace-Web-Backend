import asyncio
import json
import sys
import websockets


PrintResult = False
Result = ""


async def sendHandler(message):
    global Result
    uri = "ws://localhost:4699"
    async with websockets.connect(uri) as websocket:
        message = json.dumps(json.loads(message))
        await websocket.send(message)
        Result = await websocket.recv()
        if PrintResult:
            print(f"Received {str(Result)}")


def sendMessage(msg):
    asyncio.get_event_loop().run_until_complete(sendHandler(msg))


def getResult():
    global Result
    return Result


if __name__ == "__main__":
    if len(sys.argv) <= 1:
        print("Need a JSON string to send.")
    else:
        PrintResult = True
        sendMessage(sys.argv[1])
