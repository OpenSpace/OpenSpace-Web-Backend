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

import functools
import glob
import os
import re
import shutil
import sys
import time


"""
This script is used to copy the necessary files and directories for an additional
rendering/streaming instance. In order for the rendering server to support multiple
sessions (one session per user), there must be an OpenSpace base directory that is
dedicated to each session.
Run this script to create a single additional instance of OpenSpace streaming. It will
first verify that enough disk space exists, and will then copy the necessary dirs and
files. It also modifies a few configuration files to make the newly-copied instance
work for a specific instance id. The base OpenSpace directory that already exists as
part of this repository is id=0. Each subsequent instance has a '_s#' suffix where #
is the instance id (increments by 1). The base OpenSpace dir does not have this suffix,
but 0 is implied.
"""


# Directories and files to copy from the original 'OpenSpace' directory to the new
# 'OpenSpace_s#' instance directory
copyList_dirs = [
    "apps",
    "bin",
    "config",
    "data",
    "documentation",
    "modules",
    "scripts",
    "shaders",
    "support",
    "user"
]
copyList_files = [ "openspace.cfg" ]


def verifyCorrectOpenSpaceDir(currentDir):
    # Verify that this script runs in the proper place, with expected dirs present
    expectedDir_openspace = "OpenSpace"
    expectedDir_webGui = "OpenSpace-WebGuiFrontend"
    subs = getSubdirs(currentDir)
    if (not expectedDir_openspace in subs) or (not expectedDir_webGui in subs):
        raise Exception(f"Did not find '{expectedDir_openspace}' and "
                        f"'{expectedDir_webGui}' dirs. This script can only run in the "
                        "base OpenSpace-Web-Backend directory.")


def getSubdirs(directory):
    # Return a list of subdirectories within the directory parameter
    try:
        all_items = os.listdir(directory)
        subdirectories = [
            item for item in all_items if os.path.isdir(os.path.join(directory, item))
        ]
        return subdirectories
    except FileNotFoundError:
        print(f"Directory '{directory}' does not exist.")
        return []
    except PermissionError:
        print(f"Permission denied for directory '{directory}'.")
        return []


def calculateNewInstanceNumber(currentDir):
    """
    Compute the new instance id by looking at the current directory and examining the
    other 'OpenSpace_s#' directories and using the next available id (increment by 1).
    If a directory with the proper name exists, but is empty, then that id is used.
    """
    subs = getSubdirs(currentDir)
    newInstanceNum = 1
    for subDir in subs:
        checkInstanceExisting = f"OpenSpace_s{newInstanceNum}"
        if subDir == checkInstanceExisting:
            if any(os.scandir(f"{currentDir}/{subDir}")):
                newInstanceNum += 1
            else:
                break
    return newInstanceNum


def getAvailableDiskSpace(directory):
    total, used, free = shutil.disk_usage(directory)
    free_gb = free / (1024 ** 3) # Convert to GB
    return free_gb


def getUsedDiskSpace(directory="."):
    """
    Return the total size in GB of all files contained (including sub-direcctories)
    in the supplied path directory.
    """
    totalUsed = 0
    for dirpath, dirnames, filenames in os.walk(directory):
        for f in filenames:
            fileHandle = os.path.join(dirpath, f)
            if not os.path.islink(fileHandle):
                totalUsed += os.path.getsize(fileHandle)
    return totalUsed / (1024 ** 3) # Convert to GB


def verifyEnoughDiskSpace(scriptDir):
    diskAvailable = getAvailableDiskSpace(scriptDir)
    checkDir = f"{scriptDir}/OpenSpace"
    usedCalculation = 0
    print(f"Checking OpenSpace directory size...  ", end="", flush=True)
    for cDir in copyList_dirs:
        usedCalculation += getUsedDiskSpace(f"{checkDir}/{cDir}")
    print(f" {usedCalculation:.2f} GB.")
    bufferSpace = 0.5 # Want at least this much GB space left after copy
    if diskAvailable < (usedCalculation + bufferSpace):
        raise Exception("Not enough space on this filesystem for another instance.")


def verifyOpenSpaceSyncEnvironmentVariable():
    for key, value in os.environ.items():
        if key == "OPENSPACE_SYNC":
            return
    raise Exception("The environment variable 'OPENSPACE_SYNC' must be defined "
                    "in order to run multiple instances that share sync/. Note "
                    "that on Windows this must be defined in the User variables "
                    "rather than the system variables.")


def doIndividualDirectoryCopy(source, dest):
    try:
        shutil.copytree(source, dest)
    except FileExistsError:
        print(f"Copy destination '{dest}' already exists.")
    except FileNotFoundError:
        print(f"Source directory '{source}' does not exist.")
    except PermissionError:
        print(f"Permission denied while accessing '{source}' or '{dest}'.")
    except Exception as e:
        print(f"An error occurred: {e}")


def copyFilesToNewInstanceDirectory(sourceOpenSpaceDir, newDir):
    print(f"Copying directories:  ", end="", flush=True)
    for dir in copyList_dirs:
        doIndividualDirectoryCopy(f"{sourceOpenSpaceDir}/{dir}", f"{newDir}/{dir}")
        print(f"{dir}  ", end="", flush=True)
    for file in copyList_files:
        shutil.copyfile(f"{sourceOpenSpaceDir}/{file}", f"{newDir}/{file}")
    print("")
    print("...copying complete.")


def replaceStringInConfigFile(filePath, searchTrigger, whatToReplace, replaceWith):
    """
    Read a file, find a specific text entry, and replace that entry with another string.
    Then write the new version to the same filename.
    Usage:
      - filePath : The absolute path of the file to be read and modified.
      - searchTrigger : This is a regex string that indicates the beginning of the part
                        of the file that will be replaced. This string will NOT be
                        modified. Its purpose is to fine the right location where the
                        replacement should be made. This is useful, for example, when
                        replacing a line with a specific port number. Such a line is not
                        unique to the file, but the searchTrigger can specify replacing
                        the port number line that is directly below the line specified
                        by the search Trigger. If a match for the search trigger is not
                        found, then no text replacement will be made (no file write)
      - whatToReplace : A regex string for matching the string to replace. This string
                        will be replaced by the following parameter.
      - replaceWith : An exact (not regex) string that will replace the match for the
                      above parameter. The previous parameter and this parameter do not
                      need to be the same length.
    """
    try:
        with open(filePath, "r") as file:
            content = file.read()
        triggerMatch = re.search(searchTrigger, content)
        if triggerMatch != None:
            contentPostTrigger = content[triggerMatch.end():(triggerMatch.end() + 200)]
            matchToReplace = re.search(whatToReplace, contentPostTrigger)
            if matchToReplace != None:
                newIdx = triggerMatch.end() + matchToReplace.start()
                newContent = content[0:newIdx] + replaceWith
                finalIdx = newIdx + len(replaceWith)
                finalIdx -= (len(replaceWith) - len(matchToReplace.group(0)))
                newContent += content[finalIdx:]
                with open(filePath, "w") as file:
                    file.write(newContent)
                print(f"Modified config file '{filePath}'")
    except FileNotFoundError:
        print(f"Error: Configuration file '{filePath}' does not exist.")
    except PermissionError:
        print(f"Error: Permission denied for accessing file '{filePath}'.")
    except Exception as e:
        print(f"An unexpected error occurred when R/W file '{filePath}': {e}")


if __name__ == "__main__":
    scriptDir = os.path.realpath(os.path.dirname(__file__))
    verifyCorrectOpenSpaceDir(scriptDir)
    verifyEnoughDiskSpace(scriptDir)
    verifyOpenSpaceSyncEnvironmentVariable()
    newInstanceNum = calculateNewInstanceNumber(scriptDir)
    newInstanceDir = f"OpenSpace_s{newInstanceNum}"

    if not os.path.exists(f"{scriptDir}/{newInstanceDir}"):
        os.mkdir(f"{scriptDir}/{newInstanceDir}")
    print(f"Creating instance {newInstanceDir}.")
    copyFilesToNewInstanceDirectory(
        f"{scriptDir}/OpenSpace",
        f"{scriptDir}/{newInstanceDir}"
    )

    # Adjust config files for instance number
    replaceStringInConfigFile(
        f"{newInstanceDir}/openspace.cfg",
        r"Identifier += +\"DefaultWebSocketInterface\"",
        r"46[0-9][0-9]",
        str(4682 + newInstanceNum)
    )
    replaceStringInConfigFile(
        f"{newInstanceDir}/config/remote_gstreamer_output.json",
        r"\"webrtcid\"",
        r":.*,",
        f": {str(newInstanceNum)},"
    )
    print("Finished.")
