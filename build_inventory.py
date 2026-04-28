#!/usr/bin/env python3
"""Walk pages/A_*.html and build inventory.json + dump snapshots."""
import os, json, re, html as html_mod, sys
from pathlib import Path
from scan import (extract_components, page_template_actions, get_csrf,
                  WIRE_CLICK_RE, WIRE_SUBMIT_RE, WIRE_MODEL_RE, WIREID_RE)

PAGES = sorted(Path("pages").glob("A_*.html"))
inventory = {}
all_snaps = []

for p in PAGES:
    txt = p.read_text(errors="ignore")
    comps = extract_components(txt)
    actions = page_template_actions(txt)
    page_id = p.stem.replace("A_", "")
    for c in comps:
        snap = c["snapshot"]
        memo = snap.get("memo", {})
        name = memo.get("name", "<unknown>")
        data = snap.get("data") or []
        # data is typically a [dict, marker_dict] tuple; first element holds the props
        props = {}
        models = []
        if isinstance(data, list) and len(data) >= 1 and isinstance(data[0], dict):
            props = data[0]
        elif isinstance(data, dict):
            props = data
        # detect models within props
        def walk(v, path=""):
            res = []
            if isinstance(v, list) and len(v) == 2 and isinstance(v[1], dict) and v[1].get("s") == "mdl":
                res.append({"path": path, "class": v[1].get("class"), "key": v[1].get("key")})
            elif isinstance(v, dict):
                for k, vv in v.items():
                    res += walk(vv, f"{path}.{k}" if path else k)
            elif isinstance(v, list):
                for i, vv in enumerate(v):
                    res += walk(vv, f"{path}[{i}]")
            return res
        models = walk(props)

        snap_file = f"snapshots/{page_id}__{re.sub('[^a-zA-Z0-9]', '_', name)}.json"
        os.makedirs("snapshots", exist_ok=True)
        with open(snap_file, "w") as f:
            json.dump(snap, f, indent=2)

        entry = inventory.setdefault(name, {
            "name": name, "first_seen": page_id, "data_keys": set(),
            "model_classes": set(), "model_keys": set(),
            "children": set(), "actions_in_template": set(),
            "wire_models": set(), "snapshots": []
        })
        for k in (props.keys() if isinstance(props, dict) else []):
            entry["data_keys"].add(k)
        for m in models:
            if m.get("class"): entry["model_classes"].add(m["class"])
            if m.get("key") is not None: entry["model_keys"].add(m["key"])
        for child in (memo.get("children") or []):
            if isinstance(child, list) and len(child) >= 2:
                entry["children"].add(child[1] if isinstance(child[1], str) else str(child))
            else:
                entry["children"].add(str(child))
        entry["snapshots"].append({"page": page_id, "file": snap_file,
                                   "wire_id": memo.get("id")})
        all_snaps.append({"page": page_id, "name": name, "snap_file": snap_file})

    # Collect wire actions per page
    if comps:
        # attribute them to first component (best-effort)
        first = comps[0]["snapshot"]["memo"].get("name", "<unknown>")
        e = inventory.get(first)
        if e:
            for a in actions["wire_click"]: e["actions_in_template"].add(a)
            for a in actions["wire_submit"]: e["actions_in_template"].add(a)
            for a in actions["wire_model"]: e["wire_models"].add(a)

# Convert sets to sorted lists for JSON
def _ser(v):
    if isinstance(v, set): return sorted(v, key=str)
    if isinstance(v, dict): return {k: _ser(vv) for k, vv in v.items()}
    if isinstance(v, list): return [_ser(x) for x in v]
    return v

inv_out = {k: _ser(v) for k, v in inventory.items()}
with open("inventory.json", "w") as f:
    json.dump(inv_out, f, indent=2)

# Print summary
print(f"== {len(inv_out)} unique components ==")
for name, e in sorted(inv_out.items()):
    flag = ""
    for kw in ("admin", "staff", "mod", "manage", "internal", "super",
               "user-list", "users.index", "audit", "log", "report"):
        if kw in name.lower():
            flag = "  [*** SENSITIVE NAME ***]"
            break
    print(f"  {name}{flag}")
    print(f"     first: {e['first_seen']}")
    if e["data_keys"]: print(f"     keys:  {e['data_keys']}")
    if e["model_classes"]: print(f"     mdls:  {e['model_classes']} keys={e['model_keys']}")
    if e["actions_in_template"]: print(f"     acts:  {e['actions_in_template']}")
