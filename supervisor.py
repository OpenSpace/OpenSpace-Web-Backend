##########################################################################################
#                                                                                        #
# OpenSpace Streaming                                                                    #
#                                                                                        #
# Copyright (c) 2024                                                                     #
#                                                                                        #
# Permission is hereby granted, free of charge, to any person obtaining a copy of this   #
# software and associated documentation files (the "Software"), to deal in the Software  #
# without restriction, including without limitation the rights to use, copy, modify,     #
# merge, publish, distribute, sublicense, and/or sell copies of the Software, and to     #
# permit persons to whom the Software is furnished to do so, subject to the following    #
# conditions:                                                                            #
#                                                                                        #
# The above copyright notice and this permission notice shall be included in all copies  #
# or substantial portions of the Software.                                               #
#                                                                                        #
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,    #
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A          #
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT     #
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF   #
# CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE   #
# OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.                                          #
##########################################################################################

import argparse
import asyncio
import functools
import glob
import json
import os
import psutil
import shutil
import subprocess
import sys
if not os.name == "nt":
    import termios
    import tty
else:
    import msvcrt
import time
from threading import Thread, Timer
import websockets
from openspace import Api


class OsProcess:
    def __init__(self):
        self.state = "IDLE"
        self.handle = None
        self.stopSignal = None
        self.thread = None

    def setState(self, newState):
        self.state = newState

    def currentState(self):
        return self.state

    def setProcessHandle(self, handle):
        self.handle = handle

    def getHandle(self):
        return self.handle

    def assignStopSignal(self, signal):
        self.stopSignal = signal

    def hasStopSignaled(self):
        return self.stopSignal.is_set()

    def setThread(self, thread):
        self.thread = thread

    def thread(self):
        return self.thread

OpenSpaceExecRelativeDir = "bin/RelWithDebInfo"
OpenSpaceCfgRelativeDir = "config"
Processes = []



def setupArgparse():
    """
    Creates and sets up a parser for commandline arguments. This function returns the parsed
    arguments as a dictionary.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--openspaceDir",
        dest="osdir",
        type=str,
        help="Specifies the OpenSpace directory relative to this script.",
        default="OpenSpace",
        required=False
    )
    parser.add_argument(
        "--webGuiDir",
        dest="webguidir",
        type=str,
        help="Specifies the OpenSpace WebGuiFrontend directory relative to this script.",
        default="OpenSpace-WebGuiFrontend",
        required=False
    )
    parser.add_argument(
        "--ipaddress",
        dest="ip_addr",
        type=str,
        help="The IP address of this rendering server",
        default="155.98.19.66",
        required=False
    )
    parser.add_argument(
        "--capacity",
        dest="renderCapacity",
        type=str,
        help="The max number of simultaneous openspace instances.",
        default=3,
        required=False
    )
    args = parser.parse_args()
    return args


def runOpenspace(executable, baseDir, instanceId):
    """
    Run Openspace using the streaming SGCT configuration.
     - `executable`: The path to the OpenSpace executable that should be run
     - `baseDir`: The base path of the OpenSpace installation
     - `stopEvents_instance`: Event used to signal that this OpenSpace instance should stop
     - 'instanceId': Unique ID for this particular instance of OpenSpace
    """
    global Processes
    print(f"Starting OpenSpace ID {instanceId}")
    workingDirectory = os.path.dirname(os.path.normpath(executable))
    sgctConfigFile = os.path.normpath(f"{baseDir}/config/remote_gstreamer_output.json")
    process = subprocess.Popen(
        [
            os.path.normpath(executable),
            "--config", sgctConfigFile,
            "--profile", "default",
            "--bypassLauncher"
        ],
        cwd=workingDirectory,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE
    )
    Processes[instanceId].setProcessHandle(process)

    time.sleep(10)

    async def mainLoop():
        # Wait until Openspace has initialized
        print(f"Establishing API connection for ID {instanceId}...")
        os_api = Api("localhost", 4681)
        os_api.connect()
        openspace = await os_api.singleReturnLibrary()

    asyncio.new_event_loop().run_until_complete(mainLoop())
    Processes[instanceId].setState("RUNNING")
    print(f"OpenSpace ID {instanceId} INITIALIZING -> RUNNING")


def setTimerForDeinitializationPeriod(idStopped):
    global Processes
    Processes[idStopped].setState("IDLE")
    print("timer expired")


async def processMessage(websocket, message, openspaceBaseDir, stopEvent_main):
    global Processes
    command = message.split(" ", 1)[0]
    print(f"Received command: {command}")
    if command == "START":
        startId = -1
        for i in range(0, len(Processes)):
            if Processes[i].currentState() == "IDLE":
                startId = i
                break
        if startId != -1:
            if startId > 0:
                openspaceBaseDir = f"{openspaceBaseDir}/../OpenSpace_s{startId}"
            Processes[startId].setThread(Thread(
                    target=runOpenspace,
                    args= [
                        f"{openspaceBaseDir}/{OpenSpaceExecRelativeDir}/OpenSpace.exe",
                        openspaceBaseDir,
                        startId
                    ]
                )
            )
            Processes[startId].thread.daemon = True
            Processes[startId].thread.start()
            Processes[startId].setState("INITIALIZING")
        await sendMessage(websocket, f"{str(startId)}")
    elif command == "STOP":
        idToStop = int(message.split(" ", 1)[1])
        if idToStop < len(Processes):
            await sendMessage(websocket, f"{str(idToStop)}")
            Processes[idToStop].setState("DEINITIALIZING")
            timer = Timer(5.0, setTimerForDeinitializationPeriod, args=(idToStop,))
            timer.start()
            terminateOpenSpaceInstance(idToStop)
        else:
            await sendMessage(websocket, f"{str(-1)}")
    elif command == "STATUS":
        idForStatus = int(message.split(" ", 1)[1])
        if idForStatus < len(Processes):
            status = Processes[idForStatus].currentState()
        else:
            status = "INVALID"
        await sendMessage(websocket, status)
    elif command == "SERVER_STATUS":
        nRunning = 0
        for i in range(0, len(Processes)):
            if Processes[i] != "IDLE":
                nRunning += 1
        await sendMessage(websocket, f"{nRunning}/{len(Processes)}")
    else:
        print(f"Invalid message received: '{message}'")


def terminateOpenSpaceInstance(id):
    curr = Processes[id].currentState()
    if curr == "INITIALIZING" or curr == "RUNNING" or curr == "DEINITIALIZING":
        Processes[id].getHandle().kill()


async def sendMessage(websocket, message):
    print("Sending msg: '" + message + "'")
    await websocket.send(message)


async def receiveProcess(websocket, openspaceBaseDir, stopEvent_main):
    try:
        message = await websocket.recv()
        await processMessage(
            websocket,
            message,
            openspaceBaseDir,
            stopEvent_main
        )
    except websockets.ConnectionClosed:
        print("Connection closed")


async def websocketServer(stopEvent_main, openspaceBaseDir):
    boundHandler = functools.partial(
        receiveProcess,
        openspaceBaseDir=openspaceBaseDir,
        stopEvent_main=stopEvent_main
    )
    async with websockets.serve(boundHandler, "localhost", 4699):
        print("WebSocket server started on ws://localhost:4699")
        await stopEvent_main.wait()  # Wait until stop event is set
    print(f"Quitting websocketServer.")


def keyPressedUnix():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        return sys.stdin.read(1) #non-blocking single-char read
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def keyPressedWin():
    return msvcrt.kbhit()


def keyPressed():
    if os.name == "nt":
        return keyPressedWin()
    else:
        return keyPressedUnix()


async def webGuiFrontendServer(stopEvent, workingDir):
    execPath = os.path.normpath(workingDir)
    if os.name == "nt":
        execArgs = ["start", "powershell", "npm", "start"]
    else:
        execArgs = ["start", "gnome-terminal", "npm", "start"]
    process = subprocess.Popen(
        execArgs,
        shell=True,
        cwd=execPath,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE)
    print("Started WebGUI Frontend server.")
    # Wait for the stop signal while the process runs
    while not stopEvent.is_set():
        await asyncio.sleep(1)  # Periodically check for the stop signal

    # Stop signal received, terminate the subprocess
    await terminateProcess("node.exe", ["start"])
    await terminateProcess("node.exe", ["webpack-dev-server"])
    print("Quit WebGUI Frontend server.")


async def signalingServer(stopEvent, workingDir):
    execPath = os.path.normpath(workingDir)
    if os.name == "nt":
        execArgs = [
            "start",
            "powershell",
            "$Host.UI.RawUI.WindowTitle='signalingserver'; ",
            "node",
            "signalingserver"
        ]
    else:
        execArgs = ["start", "gnome-terminal", "node", "signalingserver"]
    process = subprocess.Popen(
        execArgs,
        shell=True,
        cwd=execPath,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE)
    print("Started signalingserver.")
    # Wait for the stop signal while the process runs
    while not stopEvent.is_set():
        await asyncio.sleep(1)  # Periodically check for the stop signal

    # Stop signal received, terminate the subprocess
    await terminateProcess("node.exe", ["signalingserver"])
    print("Quit signalingserver.")


async def terminateProcess(processName, processElems, ignoreElems=[]):
    """
    Terminate a process by its commandline elements
     - `processName`: The exact name of the process executable
     - `processElems`: An array of strings containing the commandline elements of the
                       running process. For a process to be terminated, its 'cmdline'
                       properties must contain ALL of the string elements in this array.
     - `ignoreElems`: An array of elements that will disqualify a process from being
                      terminated. If the process' cmdline elements contain any one of
                      these, then it will not be terminated.
    """
    processElems = [elem.lower() for elem in processElems]
    ignoreElems = [elem.lower() for elem in ignoreElems]
    # Iterate through all running processes
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # Check if the process command matches the target
            if not proc.info:
                continue
            if proc.info['name'].lower() != processName.lower():
                continue
            iterProcElems = proc.info['cmdline']
            fullName = f"{processName} {iterProcElems}"
            iterProcElems = [elem.lower() for elem in iterProcElems]
            if iterProcElems == None or len(iterProcElems) == 0:
                continue
            proceedWithTermination = True
            for ignore in ignoreElems:
                if any(ignore in iterProcElem for iterProcElem in iterProcElems):
                    proceedWithTermination = False
            if len(processElems) > 0:
                for elem in processElems:
                    if not any(elem in iterProcElem for iterProcElem in iterProcElems):
                        proceedWithTermination = False
            if proceedWithTermination:
                subprocess.check_output(f"Taskkill /PID {proc.info['pid']} /F")
                print(f"Terminated {fullName} with PID: {proc.info['pid']}")
                await asyncio.sleep(0.5) # Give it time to terminate
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass


async def shutdownOnKeypress(stopEvent):
    while True:
        if keyPressed():
            key = str(msvcrt.getch())
            if key == "b'q'" or key == "b'Q'":
                print("Shutting down...")
                stopEvent.set()
                break
        await asyncio.sleep(0.25)


async def shutdownTaskAndVerify(taskHandle, taskName):
    #taskHandle.cancel()
    try:
        await taskHandle
    except asyncio.CancelledError:
        print(f"Task '{taskName}' clean shutdown.")


async def mainAsync(openspaceBaseDir, openspaceFrontendDir, signalingServerDir):
    global Processes
    stopEvent_main = asyncio.Event()
    for i in range(0, len(Processes)):
        Processes[i].assignStopSignal(asyncio.Event())
    # Start the websocket server
    websocket_task = asyncio.create_task(
        websocketServer(stopEvent_main, openspaceBaseDir)
    )
    # Start the webGUI frontend node.js server
    webGuiFrontend_task = asyncio.create_task(
        webGuiFrontendServer(stopEvent_main, openspaceFrontendDir)
    )
    # Start the signaling server
    signalingserver_task = asyncio.create_task(
        signalingServer(stopEvent_main, signalingServerDir)
    )
    # Start the shutdown task on keypress
    shutdown_task = asyncio.create_task(shutdownOnKeypress(stopEvent_main))
    print("Press 'q' to stop.")
    await shutdown_task

    print("Finished waiting for shutdown_task")
    # Kill any OpenSpace instances that are running
    for i in range(0, len(Processes)):
        terminateOpenSpaceInstance(i)
    await shutdownTaskAndVerify(websocket_task, "websocket server")
    await shutdownTaskAndVerify(webGuiFrontend_task, "webGuiFrontend server")
    await shutdownTaskAndVerify(signalingserver_task, "signaling server")
    print("Exiting mainAsync.")


if __name__ == "__main__":
    args = setupArgparse()
    for i in range(0, args.renderCapacity):
        Processes.append(OsProcess())
    print(f"Render capacity: {args.renderCapacity} instances.")
    scriptDir = os.path.realpath(os.path.dirname(__file__))
    openspaceExec = f"{scriptDir}/{args.osdir}/{OpenSpaceExecRelativeDir}/OpenSpace.exe"
    if not os.path.exists(openspaceExec):
        raise Exception(f"Could not find OpenSpace exe '{openspaceExec}'")
    openspaceFrontendDir = f"{scriptDir}/{args.webguidir}"
    if not os.path.exists(openspaceFrontendDir):
        raise Exception(f"Could not find frontend gui '{openspaceFrontendDir}'")
    openspaceSignaling = f"{scriptDir}/{args.webguidir}/src/signalingserver"
    if not os.path.exists(openspaceSignaling):
        raise Exception(f"Could not find signaling server '{openspaceSignaling}'")

    asyncio.run(mainAsync(
        f"{scriptDir}/{args.osdir}",
        openspaceFrontendDir,
        openspaceSignaling)
    )
    print("Quit __main__")
