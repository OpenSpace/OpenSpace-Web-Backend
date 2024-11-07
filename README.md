# OpenSpace Web Backend

## WebRTC Rendering Server Install

Currently only a Windows 10+ system can run as an OpenSpace WebRTC Rendering Server.

After cloning this repository recursively, follow these install & configuration steps.

### Determine Server IP Address
Some of the steps below require the server’s IP address. This depends on the network configuration of the server and client:
- If the server and client are running on the same machine, then use `127.0.0.1` instead of `localhost`.
- If both machines are running on the same LAN, then the server’s LAN IP address can be used (probably starting with `192.`).
- If the client will be accessing the server from another network, then the server’s public IP, or external IP, address will be used.

### Build the OpenSpace submodule

The `feature/streaming` branch of this submodule will have been cloned. Create a build directory within the OpenSpace directory, then configure & generate it in CMake with the `SGCT_GSTREAMER_SUPPORT` checkbox enabled. Then open it in Visual Studio and build it in the *RelWithDebInfo* configuration. Verify that it builds successfully.

### Configure the OpenSpace-WebGuiFrontend submodule
1. Edit the `defaults` object in *src/api/Environment.js* to configure the settings for this server. Set `wsAddress` to the server IP address discussed above. Also set `signalingAddress` to the same IP address, since the signaling server will be running on the same machine. Leave `wsPort` and `signalingPort` at their default settings.
2. Open a terminal, cd to *OpenSpace-WebGuiFrontend/*. Run `npm install` when running first time, and ensure that there are no errors. You can add the `--legacy-peer-deps` option if there are dependency problems.
3. Setup the signaling server by opening another terminal, cd to *OpenSpace-WebGuiFrontend/src/signalingserver*, and run `npm install`.

### Install other Software
1. Download and install [Node.js](https://nodejs.org/en/) and npm if necessary.
2. Install python if not already installed.
3. Install python libraries using `pip install`:
	- openspace-api
	- websockets
	
### Networking Setup
- The WebRTC Rendering Server needs to have ports 4680 - 4700, 8443 open; not only on its own firewall but on its parent network(s).
- If the server has a hostname, enter it in the file *OpenSpace-WebGuiFrontend/package.json*, in the `"scripts"{"start"}` line. Replace `--host 0.0.0.0` with `--host your.hostname.com`.
- Ideally, the server will have an SSL certificate so that it can serve https. Certificates can be obtained from various sources, but that's a topic covered elsewhere. A certificate is preferred because browsers default to blocking streaming video from an "insecure" source. If a user connects to a WebRTC server via plain http, then the workaround for this in the user's google chrome is to browse to `chrome://flags` and add the server’s IP address & port under the “Insecure origins treated as secure” section. An address entered here should look like `http://192.168.1.39:4690`. Note that this step is not necessary if running both the Server and Viewer on the same machine using 127.0.0.1.

## Supervisor

### Overview 
The Supervisor is a python application that runs indefinitely on the WebRTC Rendering Server.

This application communicates with the Web Backend Server via websocket port 4699. It listens for commands from the Web Backend Server, and only sends messages when responding. A full list of commands is shown in the API document linked below in the **Supervisor Communications** section.

The application handles the running of OpenSpace instance(s) as requested. It also runs the OpenSpace WebGui Frontend, and the signaling server.

### How to Run the Supervisor
To run, open a windows terminal, cd to the base directory of the OpenSpace-Web-Backend repo, and enter `python supervisor.py`. It will run the OpenSpace WebGui Frontend in a new terminal window using node.js. It will also run the signaling server in a separate terminal window. Internally, it will run a websocket server to communicate with the web backend server.

To exit the Supervisor, press `q` in its terminal window. It will automatically shut down any running OpenSpace instances, and will also stop the WebGui Frontend and signaling server.

If desired, the Supervisor can be set as an application that automatically runs on startup.

### Supervisor Communications
[This API document](https://docs.google.com/document/d/1B5lUBf3817arQpV4Vdz7yopb8SBSFIK_DrQTK7n07ns) shows the overall architecture and the Supervisor's place within it. The document also lists all message types, and a typical handshake diagram between the different components in the streaming setup.

The *testing/* subdirectory in this repo contains scripts to send messages to the supervisor for test purposes when running the server manually.

## Adding an OpenSpace Instance on the WebRTC Rendering Server
A rendering server is designed to simultaneously run multiple instances of OpenSpace--one for each user/session. In order for it to run smoothly, this requires that each instance have its own install directory, with executables, configuration files, etc.

This repository has the first OpenSpace instance already included as a submodule, and as stated above this must be compiled initially. After this, additional instance(s) can be created using the *add_rendering_instance.py* script. This script is run once in order to create a single additional instance on the rendering server. It can be run again to support another individual user/session, and so on. There is, of course, a limit to how many simultaneous sessions that the server's hardware can support while still providing a reasonable framerate and responsiveness. The script does not enforce such a limit; it is up to the user to decide how many simultaneous instances can run.

Individual sessions are tracked using the session id, which is a zero-based index. The pre-existing *OpenSpace/* directory corresponds to id 0 (but does not contain it in the name as the other instances do). When a new instance is added, the script creates a new directory using the pattern *OpenSpace_s#/* where # is the index. It determines the new instance's id based on how many instance directories already exist. The script only copies certain directories and files (specified in the script) from the base *OpenSpace/* directory. It will only make the copies if enough disk space is available. The *add_rendering_instance.py* script also modifies a few configuration files based on the id. It sets the websocket comms to a unique port for the instance in *openspace.cfg*, and a unique `webrtcid` value in *config/remote_gstreamer_output.json*. It also enforces the rule that the server must have the `OPENSPACE_SYNC` environment variable defined so that all instances share the same *sync/* folder. If the environment variable doesn't exist, it won't create the new instance.

## Viewing OpenSpace Streaming in a Browser
When all of the servers are working together, a user will connect to the Web Frontend Server and go through an easy-to-use interface. When the OpenSpace streaming session runs, their browser will internally open a URL to the rendering server; the user will not need to enter or see this URL.

If someone were to enter this manually in a browser, it would look like:<br>`192.168.1.44:4690/frontend/#/streaming?id=0`<br>

Here, the URL parameter `id` is the unique zero-based ID discussed in the API document mentioned above (defaults to zero if not provided).

Once the WebGui loads in the browser, open the streaming menu (icon of a computer with an arrow on it), and click "Join session". Note that this step may be automated-away in the future.

If there is a problem, refresh the browser and Join the session again. It won’t be necessary to restart the other components.

## Notes

### OpenSpace Running in WebRTC Rendering Server
Two separate OpenSpace windows run with a single instance of OpenSpace. This is necessary for the frame encoding; with only one window running, most frames are dropped.

#### Adjustments to Video Quality
Currently the streaming framerate runs as high as possible, but with multiple instances running, frames will be dropped (manifests as blinking black frames). To prevent this, go to `Settings -> Render Engine -> Framerate Limit` in the WebGui and set to 30 fps or so.

Video resolution can be set in the `config/remote_gstreamer_output.json` sgct configuration file (side note: currently this file is the only config file that the WebRTC streaming version can run). Set the `"size"` values in both window entries to the desired resolution.

The WebRTC streaming version of OpenSpace uses a hardware-accelerated nvidia encoder for h264 video. The configuration pipeline for this encoder can be found in the `pipelineDescription` string of the _apps/OpenSpace/ext/sgct/ext/gstreamer/gstreamerWebRTC.h_ file. There are multiple settings that can be experimented with (including bitrate, preset, etc.) in order to find a balance between streaming performance and video quality.

