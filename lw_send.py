#!/usr/bin/env python3
"""Helpers for sending Livewire 3 update requests via curl subprocess."""
import subprocess, json, re, sys, html as html_mod, os, time
from pathlib import Path

BASE = "https://gainledgecapital.com"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"


def curl(jar, method, url, body=None, headers=None, save=None,
         max_bytes=200_000):
    """Always write response body to a file, then read first max_bytes."""
    import tempfile
    fd, tmp = tempfile.mkstemp(prefix="curl-", suffix=".out")
    os.close(fd)
    cmd = ["curl", "-sS", "-c", jar, "-b", jar,
           "--max-filesize", "300000",
           "--max-time", "30",
           "-H", f"User-Agent: {UA}",
           "-X", method, url, "-o", tmp]
    headers = headers or {}
    for k, v in headers.items():
        cmd += ["-H", f"{k}: {v}"]
    if body is not None:
        cmd += ["--data-binary", body]
    cmd += ["-w", "%{http_code}"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    code = int(p.stdout.strip()) if p.stdout.strip().isdigit() else -1
    full = open(tmp, "rb").read()
    bodyout = full[:max_bytes].decode("utf-8", errors="replace")
    if save:
        Path(save).write_bytes(full)
    os.unlink(tmp)
    return code, bodyout


def fetch_page(jar, path):
    code, body = curl(jar, "GET", BASE + path)
    return code, body


def get_csrf(html_text):
    m = re.search(r'<meta name="csrf-token" content="([^"]+)"', html_text)
    return m.group(1) if m else None


def find_component(html_text, name):
    """Return raw snapshot string + parsed dict for component name."""
    snap_re = re.compile(r'wire:snapshot="((?:[^"\\]|\\.)*)"')
    for m in snap_re.finditer(html_text):
        raw = html_mod.unescape(m.group(1))
        try:
            parsed = json.loads(raw)
        except Exception:
            continue
        if parsed.get("memo", {}).get("name") == name:
            return raw, parsed
    return None, None


def lw_update(jar, snapshot_raw, updates, calls=None, csrf=None, referer=None,
              save=None):
    """Send a Livewire update with the given snapshot + updates + calls."""
    payload = {
        "_token": csrf,
        "components": [{
            "snapshot": snapshot_raw,
            "updates": updates or {},
            "calls": calls or []
        }]
    }
    headers = {
        "Content-Type": "application/json",
        "X-Livewire": "",
        "Origin": BASE,
        "Referer": referer or (BASE + "/user/dashboard"),
    }
    code, body = curl(jar, "POST", BASE + "/livewire/update",
                      body=json.dumps(payload), headers=headers, save=save)
    try:
        parsed = json.loads(body)
    except Exception:
        parsed = None
    return code, parsed, body


def fresh_component(jar, page_path, comp_name):
    """Fetch page, return (csrf, snap_raw, snap_parsed)."""
    code, html_text = fetch_page(jar, page_path)
    if code != 200:
        raise RuntimeError(f"GET {page_path} -> {code}")
    csrf = get_csrf(html_text)
    snap_raw, snap_parsed = find_component(html_text, comp_name)
    if not snap_raw:
        raise RuntimeError(f"component {comp_name!r} not on {page_path}")
    return csrf, snap_raw, snap_parsed


def summarize(parsed):
    """Compress a Livewire response to the interesting bits."""
    if parsed is None:
        return "<unparsed>"
    if "components" not in parsed:
        return json.dumps(parsed)[:600]
    comps = parsed.get("components", [])
    out = []
    for c in comps:
        snap = c.get("snapshot")
        eff = c.get("effects") or {}
        if isinstance(snap, str):
            try:
                snap = json.loads(snap)
            except Exception:
                pass
        memo = (snap or {}).get("memo", {}) if isinstance(snap, dict) else {}
        data = (snap or {}).get("data") if isinstance(snap, dict) else None
        out.append({
            "name": memo.get("name"),
            "errors": memo.get("errors"),
            "html_excerpt": (eff.get("html") or "")[:200] if isinstance(eff.get("html"), str) else None,
            "redirect": eff.get("redirect"),
            "dispatches": eff.get("dispatches"),
            "returns": eff.get("returns"),
            "data_excerpt": {k: v for k, v in (data or {}).items()
                             if k in ("name","email","role","is_admin","permissions",
                                      "balance","balanceUsd","status","kyc_status",
                                      "verified","tier","level","stripe_id",
                                      "active_tab","error","loading","subscription_tier",
                                      "user_type","type","api_token","remember_token")}
                             if isinstance(data, dict) else None,
        })
    return out


if __name__ == "__main__":
    sub = sys.argv[1]
    if sub == "test":
        jar = sys.argv[2]; path = sys.argv[3]; comp = sys.argv[4]
        csrf, raw, parsed = fresh_component(jar, path, comp)
        print("CSRF:", csrf[:20])
        print("Component data keys:",
              list((parsed.get("data") or {}).keys())
              if isinstance(parsed.get("data"), dict) else "(no dict)")
