import json
import sys
import testSend as ts

def getStatusForId(id):
    ts.sendMessage("{\"command\": \"STATUS\", \"id\": " + str(id) + "}")
    rsp = json.loads(ts.getResult())
    return rsp["status"]

if len(sys.argv) > 1:
    # If id is provided do the specific status call
    status = getStatusForId(sys.argv[1])
    print(f"Status of instance id {sys.argv[1]}: '{status}'")
else:
    # If no id provided, then find the highest non-idle id # and return its status
    ts.sendMessage("{\"command\": \"SERVER_STATUS\"}")
    capacity = ts.getResult()
    jResult = json.loads(capacity)
    for i in range(jResult["total"], 0, -1):
        status = getStatusForId(str(i - 1))
        if status != "IDLE":
            print(f"Status of instance id {(i - 1)}: '{status}'")
            quit()
    print("No running instances found.")