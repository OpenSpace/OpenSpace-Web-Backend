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
from enum import Enum, auto
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


"""
This Supervisor script continuously runs on a streaming rendering server.
Upon startup, it starts the WebGUI Frontend served by node.js in a separate terminal,
and the WebRTC signaling server in another terminal.
It communicates with a web backend server via a websocket connection. It sends messages
only as a response to received commands.
A separate API document covers the API and functionality in greater detail.
"""


OpenSpaceExecRelativeDir = "bin/RelWithDebInfo"
OpenSpaceCfgRelativeDir = "config"
Processes = []
RunOpenSpaceInShell = False

class State(Enum):
    # Running state for an OpenSpace instance
    IDLE = auto()
    INITIALIZING = auto()
    RUNNING = auto()
    DEINITIALIZING = auto()
    INVALID = auto()


class OsProcess:
    """
    Class for running and tracking an individual OpenSpace executable instance,
    with the state and thread it runs in.
    """
    def __init__(self):
        self.state = State.IDLE
        self.handle = None
        self.pid_OpenSpace = None
        self.pid_ParentShell = None
        self.stopSignal = None
        self.thread = None

    def setState(self, newState):
        self.state = newState

    def currentState(self):
        return self.state

    def currentStateString(self):
        if self.state == State.IDLE:
            return "IDLE"
        elif self.state == State.INITIALIZING:
            return "INITIALIZING"
        elif self.state == State.RUNNING:
            return "RUNNING"
        elif self.state == State.DEINITIALIZING:
            return "DEINITIALIZING"
        else:
            return "INVALID"

    def setProcessHandle(self, handle):
        self.handle = handle

    def getHandle(self):
        return self.handle

    def setPidOpenSpace(self, pid):
        self.pid_OpenSpace = pid

    def pidOpenSpace(self):
        return self.pid_OpenSpace

    def setPidParentShell(self, pid):
        self.pid_ParentShell = pid

    def pidParentShell(self):
        return self.pid_ParentShell

    def assignStopSignal(self, signal):
        self.stopSignal = signal

    def hasStopSignaled(self):
        return self.stopSignal.is_set()

    def setThread(self, thread):
        self.thread = thread

    def thread(self):
        return self.thread

    def reset(self):
        self.__init__()


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
    openspaceArgs = []
    if RunOpenSpaceInShell:
        openspaceArgs = ["start"]
        if os.name == "nt":
            openspaceArgs.extend(["powershell", "$Host.UI.RawUI.WindowTitle='OpenSpace'; "])
        else:
            openspaceArgs.append("gnome-terminal")
    openspaceArgs.extend([
        os.path.normpath(executable),
        "--config", sgctConfigFile,
        "--profile", "default",
        "--bypassLauncher"
    ])
    process = subprocess.Popen(
        openspaceArgs,
        shell=True,
        cwd=workingDirectory,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE
    )
    if RunOpenSpaceInShell:
        time.sleep(4) #Wait for it to start OpenSpace
        Processes[instanceId].setPidOpenSpace(None)
        Processes[instanceId].setPidParentShell(None)
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                # Check if the process command matches the target
                if not proc.info:
                    continue
                if proc.info['name'].lower() == 'powershell.exe':
                    parent = psutil.Process(proc.pid)
                    children = parent.children(recursive=False)
                    for child in children:
                        if child.name():
                            if child.name().lower() == "openspace.exe":
                                msg = f"Found powershell pid {proc.pid}" \
                                    f" with OpenSpace.exe child ({child.pid})."
                                Processes[instanceId].setPidOpenSpace(child.pid)
                                Processes[instanceId].setPidParentShell(proc.pid)
                                print(msg)
                                break
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                print("exception with ps info")
                pass
    else:
        Processes[instanceId].setProcessHandle(process)
    time.sleep(10)

    async def mainLoop():
        # Loop for waiting until Openspace has initialized
        print(f"Establishing API connection for ID {instanceId}...")
        os_api = Api("localhost", 4681)
        os_api.connect()
        openspace = await os_api.singleReturnLibrary()

    asyncio.new_event_loop().run_until_complete(mainLoop())
    Processes[instanceId].setState(State.RUNNING)
    print(f"OpenSpace ID {instanceId} INITIALIZING -> RUNNING")

    async def waitForInstanceToStopByPid(procPid):
        while psutil.pid_exists(procPid):
            await asyncio.sleep(2.0)

    async def waitForInstanceToStopByHandle(procHandle):
        while procHandle.poll() is None:
            await asyncio.sleep(2.0)

    # Wait until this OpenSpace instance has stopped (e.g. via the frontend gui)
    if RunOpenSpaceInShell:
        asyncio.new_event_loop().run_until_complete(
            waitForInstanceToStopByPid(Processes[instanceId].pidOpenSpace())
        )
    else:
        asyncio.new_event_loop().run_until_complete(
            waitForInstanceToStopByHandle(process)
        )
    Processes[instanceId].setState(State.IDLE)
    print(f"OpenSpace ID {instanceId} RUNNING -> IDLE")


def setTimerForDeinitializationPeriod(idStopped):
    global Processes
    Processes[idStopped].setState(State.IDLE)
    print("timer expired")


async def processMessage(websocket, message, openspaceBaseDir):
    """
    Handle JSON messages from web backend, execute command, then send response
    """
    global Processes
    try:
        json_data = json.loads(message)
        command = json_data['command']
        print(f"Received command: {command}")
        result = json.loads("""{
            "command": "START",
            "error": "none",
            "id": 0
        }""")
        result['command'] = command # echo the command back
        if command == "START":
            startId = -1
            for i in range(0, len(Processes)):
                if Processes[i].currentState() == State.IDLE:
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
                Processes[startId].setState(State.INITIALIZING)
            else:
                result['error'] = "no available slots"
            result['id'] = startId
            await sendMessage(websocket, json.dumps(result))
        elif command == "STOP":
            idToStop = json_data['id']
            result['id'] = idToStop
            if idToStop < len(Processes):
                if Processes[idToStop].currentState() == State.IDLE:
                    result['error'] = "not running"
                await sendMessage(websocket, json.dumps(result))
                if Processes[idToStop].currentState() != State.IDLE:
                    Processes[idToStop].setState(State.DEINITIALIZING)
                    timer = Timer(5.0, setTimerForDeinitializationPeriod, args=(idToStop,))
                    timer.start()
                    if RunOpenSpaceInShell:
                        await terminateOpenSpaceInstanceInShell(idToStop)
                        Processes[idToStop].reset()
                    else:
                        terminateOpenSpaceInstance(idToStop)
            else:
                result['error'] = "invalid id"
                await sendMessage(websocket, json.dumps(result))
        elif command == "STATUS":
            idForStatus = json_data['id']
            if idForStatus < len(Processes) and idForStatus >= 0:
                result['status'] = Processes[idForStatus].currentStateString()
            else:
                result['status'] = State.INVALID
                result['error'] = "invalid id"
            await sendMessage(websocket, json.dumps(result))
        elif command == "SERVER_STATUS":
            nRunning = 0
            for i in range(0, len(Processes)):
                if Processes[i].currentState() != State.IDLE:
                    nRunning += 1
            result['running'] = nRunning
            result['total'] = len(Processes)
            await sendMessage(websocket, json.dumps(result))
        else:
            print(f"Invalid message received: '{message}'")
            await sendMessage(
                websocket,
                json.dumps({"error": f"invalid message received: {command}"})
            )
    except json.JSONDecodeError as e:
        print(f"JSON decode error {e}")
        await sendMessage(
            websocket,
            json.dumps({"error": "json decode error"})
        )


def terminateOpenSpaceInstance(id):
    c = Processes[id].currentState()
    if c == State.INITIALIZING or c == State.RUNNING or c == State.DEINITIALIZING:
        Processes[id].getHandle().kill()


async def terminateOpenSpaceInstanceInShell(id):
    c = Processes[id].currentState()
    if c == State.INITIALIZING or c == State.RUNNING or c == State.DEINITIALIZING:
        if Processes[id].pidOpenSpace():
            p = psutil.Process(Processes[id].pidParentShell())
            terminateProcessByPid(Processes[id].pidParentShell())
            p.kill()
            p.terminate()
            await asyncio.sleep(2)
            p = psutil.Process(Processes[id].pidOpenSpace())
            p.kill()
            p.terminate()
        else:
            print(f"Unable to terminate OpenSpace via its parent shell pid "
                  f"{Processes[id].pidParentShell()}")


async def sendMessage(websocket, message):
    print("Sending msg: '" + message + "'")
    await websocket.send(message)


async def receiveProcess(websocket, openspaceBaseDir):
    try:
        message = await websocket.recv()
        await processMessage(
            websocket,
            message,
            openspaceBaseDir
        )
    except websockets.ConnectionClosed:
        print("Connection closed")


async def websocketServer(stopEvent_main, openspaceBaseDir):
    boundHandler = functools.partial(
        receiveProcess,
        openspaceBaseDir=openspaceBaseDir
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
    """
    Start WebGUI Frontend node.js server in the workingDir in a separate terminal.
    Runs until the stopEvent signal is set.
    """
    execPath = os.path.normpath(workingDir)
    execArgs = ["start", "powershell", "npm", "start"]
    if os.name != "nt":
        execArgs[1] = "gnome-terminal"
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
    """
    Start WebRTC signaling server in the workingDir in a separate terminal.
    Runs until the stopEvent signal is set.
    """
    execPath = os.path.normpath(workingDir)
    execArgs = ["start"]
    if os.name == "nt":
        execArgs.extend(["powershell", "$Host.UI.RawUI.WindowTitle='signalingserver'; "])
    else:
        execArgs.append("gnome-terminal")
    execArgs.extend(["node", "signalingserver"])
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
                if RunOpenSpaceInShell:
                    terminateProcessByPid(proc.info['pid'])
                else:
                    subprocess.check_output(f"Taskkill /PID {proc.info['pid']} /F")
                print(f"Terminated {fullName} with PID: {proc.info['pid']}")
                await asyncio.sleep(0.5) # Give it time to terminate
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass


def terminateProcessByPid(pidToTerminate):
    """
    Terminate a process by its pid. Some processes don't seem to respond to psutil.kill,
    so this function uses a windows 'Taskkill /PID # /F' command.
     - `pidToTerminate`: The process pid that will be terminated.
    """
    subprocess.check_output(f"Taskkill /PID {pidToTerminate} /F")


async def shutdownOnKeypress(stopEvent):
    """
    If 'q' key is pressed, signal the stopEvent which is used to stop other processes
    """
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
    """
    Main asynchronous loop to run:
      server for websocket comms with web backend
      WebGUI frontend node.js server
      WebRTC signaling server
    After starting these processes, waits for a keypress to initiate shutdown.
    Parameters:
      - openspacceBaseDir : absolute path to the base dir of the OpenSpace installation
      - openspaceFrontendDir : absolute path to the base dir of WebGUI Frontend
      - signalingServerDir : absolute path to the directory where the signaling server
                             code resides (currently within the WebGUI Frontend dir)
    """
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
        if RunOpenSpaceInShell:
            await terminateOpenSpaceInstanceInShell(i)
            Processes[i].reset()
        else:
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
