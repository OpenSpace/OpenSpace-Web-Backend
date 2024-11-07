import json
import testSend as ts

ts.sendMessage("{\"command\": \"SERVER_STATUS\"}")
capacity = ts.getResult()
jResult = json.loads(capacity)
for i in range(jResult["total"], 0, -1):
    ts.sendMessage("{\"command\": \"STOP\", \"id\": " + str(i - 1) + "}")
    rsp = json.loads(ts.getResult())
    if rsp["error"] == "none":
        print(f"Stopped id {(i - 1)}")
        quit()
print("No running instances found.")