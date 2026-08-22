#!/usr/bin/env python3
"""Canonical, read-only parser for Rozoro append-only handoffs."""
import argparse, json, os, re, sys

TURN = re.compile(r"^## turn ([1-9][0-9]*)(?:\s+—.*)?$")
H2 = re.compile(r"^## ")
FIELD = re.compile(r"^([A-Za-z][A-Za-z-]*):\s*(.*)$")
KNOWN = {"verdict", "reason", "did", "pending", "inputs-needed", "artifacts"}
REQUIRED = {"verdict", "did", "pending", "inputs-needed", "artifacts"}
VERDICTS = {"done", "waiting", "needs-action", "failed", "blocked"}
NONE = {"", "none", "n/a", "na", "-"}
OPEN = {"needs-action", "failed", "blocked"}

def cursor(path):
    if not path or not os.path.exists(path): return None
    try:
        value = int(open(path).read().strip())
        if value < 0: raise ValueError()
        return value
    except Exception: return "invalid"

def parse(path, ack_v2=None, ack_legacy=None):
    try: text = open(path, encoding="utf-8").read()
    except FileNotFoundError: text = ""
    lines = text.splitlines()
    starts=[]; legacy=[]
    for i,line in enumerate(lines):
        if H2.match(line): legacy.append(i)
        m=TURN.match(line)
        if m: starts.append((i,int(m.group(1))))
    blocks=[]; errors=[]; previous=0
    for n,(start,declared) in enumerate(starts):
        end=starts[n+1][0] if n+1<len(starts) else len(lines)
        fields={}; duplicates=[]
        for line in lines[start+1:end]:
            m=FIELD.match(line)
            if m and m.group(1).lower() in KNOWN:
                key=m.group(1).lower()
                if key in fields: duplicates.append(key)
                else: fields[key]=m.group(2).strip()
        be=[]
        if declared != previous+1: be.append("turn sequence expected %d, got %d"%(previous+1,declared))
        previous=declared
        for key in sorted(REQUIRED-set(fields)): be.append("missing field: "+key)
        for key in sorted(set(duplicates)): be.append("duplicate field: "+key)
        verdict=fields.get("verdict","").lower()
        if verdict not in VERDICTS: be.append("unknown verdict: "+(fields.get("verdict") or "(missing)"))
        if verdict != "done" and not fields.get("reason","").strip(): be.append("missing field: reason")
        if verdict == "waiting":
            if fields.get("inputs-needed","").strip().lower() not in NONE: be.append("waiting requires inputs-needed: none")
            if fields.get("pending","").strip().lower() in NONE: be.append("waiting requires useful pending")
            if fields.get("reason","").strip().lower() in NONE: be.append("waiting requires useful reason")
        idx=n+1
        errors.extend("block %d: %s"%(idx,e) for e in be)
        blocks.append({"index":idx,"turn":declared,"heading":lines[start][3:].strip(),"fields":fields,"valid":not be,"errors":be,"legacy_index":legacy.index(start)+1})
    malformed=[lines[i] for i in legacy if not TURN.match(lines[i])]
    if malformed: errors.append("noncanonical H2 heading(s): "+", ".join(malformed))
    v2=cursor(ack_v2); old=cursor(ack_legacy); source="none"; acked=0
    if v2 is not None:
        source="v2"; acked=v2
        if v2=="invalid" or v2>len(blocks): errors.append("invalid canonical acknowledgement cursor"); acked=0
    elif old is not None:
        source="legacy-mapped"
        if old=="invalid" or old>len(legacy): errors.append("invalid legacy acknowledgement cursor"); acked=0
        else: acked=sum(1 for b in blocks if b["legacy_index"]<=old)
    open_items=[]
    for b in blocks:
        f=b["fields"]; inp=f.get("inputs-needed","").strip().lower()
        if b["index"]>acked and (f.get("verdict","").lower() in OPEN or inp not in NONE):
            open_items.append({"index":b["index"],"turn":b["turn"],"heading":b["heading"],"verdict":f.get("verdict",""),"inputs_needed":f.get("inputs-needed","")})
    latest=blocks[-1] if blocks else None
    return {"blocks":len(blocks),"legacy_headings":len(legacy),"acked_through":acked,"acked_source":source,"latest":latest,"block_details":blocks,"open_items":open_items,"unresolved":len(open_items),"protocol_errors":errors}

def main():
    p=argparse.ArgumentParser(); p.add_argument("handoff"); p.add_argument("--acked-v2"); p.add_argument("--acked-legacy")
    a=p.parse_args(); print(json.dumps(parse(a.handoff,a.acked_v2,a.acked_legacy),sort_keys=True,separators=(",",":")))
if __name__=="__main__": main()
