import json
import testSend as ts

ts.sendMessage("{\"command\": \"SERVER_STATUS\"}")
capacity = ts.getResult()
jResult = json.loads(capacity)
print(f"Found {jResult["running"]} running instance(s).")
