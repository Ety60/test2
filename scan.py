#!/usr/bin/env python3
"""
gainledgecapital Livewire scanner helpers.
Uses subprocess curl (Python's TLS keeps hitting upstream Envoy 503) and a cookie jar.
"""
import subprocess, re, json, html as html_mod, urllib.parse, os, time, sys, hashlib

BASE = "https://gainledgecapital.com"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"


def curl(jar, method, url, headers=None, data=None, raw_data=None,
        allow_redirects=True, save_to=None, extra=None, timeout=30):
    cmd = ["curl", "-sS", "-c", jar, "-b", jar,
           "-H", f"User-Agent: {UA}",
           "-H", "Accept-Language: en-US,en;q=0.9"]
    if not allow_redirects:
        pass  # default
    cmd += ["-X", method, url]
    if headers:
        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]
    if raw_data is not None:
        cmd += ["--data-binary", raw_data]
    elif data is not None:
        if isinstance(data, dict):
            for k, v in data.items():
                cmd += ["--data-urlencode", f"{k}={v}"]
        else:
            cmd += ["--data-binary", data]
    cmd += ["-w", "\n__HTTP__%{http_code}__LOC__%header{location}__"]
    if extra:
        cmd += extra
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    out = proc.stdout
    m = re.search(r"\n__HTTP__(\d+)__LOC__([^_]*)__$", out)
    code = int(m.group(1)) if m else -1
    loc = (m.group(2) if m else "") or ""
    body = out[:m.start()] if m else out
    if save_to:
        with open(save_to, "w") as f:
            f.write(body)
    return code, loc, body, proc.stderr


def log_request(meta):
    with open("request_log.jsonl", "a") as f:
        f.write(json.dumps(meta) + "\n")


# Snapshot handling
SNAPSHOT_RE = re.compile(r'wire:snapshot="((?:[^"\\]|\\.)*)"')
WIREID_RE = re.compile(r'wire:id="([^"]+)"')
EFFECTS_RE = re.compile(r'wire:effects="((?:[^"\\]|\\.)*)"')
WIRE_CLICK_RE = re.compile(r'wire:click="([^"]+)"')
WIRE_SUBMIT_RE = re.compile(r'wire:submit(?:\.[a-z]+)?="([^"]+)"')
WIRE_MODEL_RE = re.compile(r'wire:model(?:\.[a-z.]+)?="([^"]+)"')


def html_decode(s):
    return html_mod.unescape(s)


def extract_components(html_text):
    """Return list of {wire_id, snapshot_json (dict), effects (dict), raw_snapshot_str}."""
    out = []
    # Find each wire:snapshot, and pair with the nearest preceding wire:id within ~2KB
    for m in SNAPSHOT_RE.finditer(html_text):
        snap_raw = html_decode(m.group(1))
        try:
            snap = json.loads(snap_raw)
        except Exception:
            continue
        # back-reference for wire:id
        start = max(0, m.start() - 4000)
        ctx = html_text[start:m.end()]
        wid_m = list(WIREID_RE.finditer(ctx))
        wid = wid_m[-1].group(1) if wid_m else None
        out.append({"wire_id": wid, "snapshot": snap, "raw": snap_raw})
    return out


def page_template_actions(html_text):
    return {
        "wire_click": sorted(set(WIRE_CLICK_RE.findall(html_text))),
        "wire_submit": sorted(set(WIRE_SUBMIT_RE.findall(html_text))),
        "wire_model": sorted(set(WIRE_MODEL_RE.findall(html_text))),
    }


def get_csrf(html_text):
    m = re.search(r'<meta name="csrf-token" content="([^"]+)"', html_text)
    if m:
        return m.group(1)
    m = re.search(r'name="_token"[^>]*value="([^"]+)"', html_text)
    return m.group(1) if m else None


def fetch(jar, path, save=True):
    url = path if path.startswith("http") else BASE + path
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", path).strip("_") or "root"
    out_path = f"pages/{safe}.html"
    code, loc, body, err = curl(jar, "GET", url, save_to=out_path if save else None)
    log_request({"ts": time.time(), "jar": jar, "method": "GET", "url": url,
                 "code": code, "loc": loc, "saved": out_path if save else None})
    return code, loc, body


def livewire_update(jar, csrf, components, referer=None, save_to=None):
    """components = list of {snapshot:str, updates:dict, calls:list}."""
    payload = {"_token": csrf, "components": components}
    headers = {
        "Content-Type": "application/json",
        "X-Livewire": "",
        "X-CSRF-TOKEN": csrf,
        "Origin": BASE,
    }
    if referer:
        headers["Referer"] = referer
    body = json.dumps(payload)
    code, loc, resp, err = curl(jar, "POST", BASE + "/livewire/update",
                                headers=headers, raw_data=body, save_to=save_to)
    log_request({"ts": time.time(), "jar": jar, "method": "POST",
                 "url": BASE + "/livewire/update",
                 "code": code, "loc": loc,
                 "saved": save_to,
                 "components_count": len(components)})
    return code, resp


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "fetch":
        jar, path = sys.argv[2], sys.argv[3]
        code, loc, body = fetch(jar, path)
        print(f"{code} {loc}  ({len(body)} bytes)")
    elif cmd == "snap":
        # Show all snapshots from a saved page
        path = sys.argv[2]
        with open(path) as f:
            html_text = f.read()
        comps = extract_components(html_text)
        for c in comps:
            print("=" * 60)
            print(f"wire:id = {c['wire_id']}")
            print(json.dumps(c["snapshot"], indent=2)[:4000])
    elif cmd == "csrf":
        path = sys.argv[2]
        with open(path) as f:
            print(get_csrf(f.read()))
    else:
        print("Usage: scan.py {fetch|snap|csrf} ...")
