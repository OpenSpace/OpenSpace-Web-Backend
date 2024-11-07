import json
import testSend as ts

ts.sendMessage("{\"command\": \"SERVER_STATUS\"}")
capacity = ts.getResult()
jResult = json.loads(capacity)
for i in range(jResult["total"], 0, -1):
    ts.sendMessage("{\"command\": \"STATUS\", \"id\": " + str(i - 1) + "}")
    rsp = json.loads(ts.getResult())
    if rsp["status"] != "IDLE":
        print(f"Status of instance id {(i - 1)}: '{rsp["status"]}'")
        quit()
print("No running instances found.")