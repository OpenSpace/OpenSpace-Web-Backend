#!/bin/bash

set -e
set -x

# Navigate to OpenSpace-WebGuiFrontend and run npm install
cd OpenSpace-WebGuiFrontend
npm install

# Navigate to src/signalingserver and run npm install
cd src/signalingserver
npm install