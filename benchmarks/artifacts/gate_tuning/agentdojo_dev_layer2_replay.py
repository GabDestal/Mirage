import json, sys
from engine.detection import decision_model as d
E = "/tmp/mirage-adv2-evidence/"
for f in ["user_task_1:injection_task_1.gate.38a48a.json", "user_task_8:injection_task_1.gate.551e32.json",
          "user_task_18:injection_task_3.gate.defdcd.json"]:
    ev = json.load(open(E + f))
    task = next(b["text"] for m in ev["messages"] if m["role"] == "user" for b in m["content"] if "text" in b)
    results = [b["toolResult"]["content"][0].get("text") for m in ev["messages"] for b in m["content"] if "toolResult" in b]
    hist = []
    for i, g in enumerate(ev["gate_decisions"]):
        if g["layer"] == "decision_model" or (d.outbound(g["tool"], g["args"]) and g["decision"] == "allow"):
            v = d.classify("slack", task, g["tool"], g["args"], sys.argv[1], context=hist)
            print(f"{f[:28]:28} {g['tool']:20} was={g['decision']:5}/{g.get('policy_id')} now={v.get('violates')}/{v.get('p')}/{v.get('policy_id') or v.get('unavailable')} {v.get("reason")}", flush=True)
        if i < len(results):
            hist.append({"tool": g["tool"], "args": g["args"], "result": results[i]})
