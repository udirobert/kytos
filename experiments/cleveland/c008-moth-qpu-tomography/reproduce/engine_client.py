"""Moth engine API client — upload assets, submit jobs, poll results.

Reads MOTH_API_KEY from the environment. Used to produce the derived
artifacts (teleblur morph, qpixl read-back, retrocausal echo) recorded in
metrics/summary.json -> derived_artifacts."""

import json
import os
import subprocess
import sys
import time

API = "https://api.mothquantum.com/api/v1"
KEY = os.environ["MOTH_API_KEY"]


def api(method, path, body=None):
    args = ["curl", "-s", "-X", method, "-H", f"Authorization: Bearer {KEY}"]
    if body is not None:
        args += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]
    out = subprocess.run(args + [API + path], capture_output=True, text=True)
    return json.loads(out.stdout) if out.stdout.strip() else {}


def upload(path, content_type="image/png", filename=None):
    data_size = os.path.getsize(path)
    filename = filename or os.path.basename(path)
    a = api(
        "POST",
        "/assets",
        {
            "filename": filename,
            "content_type": content_type,
            "size_bytes": data_size,
        },
    )
    aid = a["asset_id"]
    up = a["upload"]
    cmd = ["curl", "-s", "-X", up["method"], "-T", path]
    for k, v in up.get("headers", {}).items():
        cmd += ["-H", f"{k}: {v}"]
    cmd.append(up["url"])
    subprocess.run(cmd, capture_output=True, check=True)
    api("POST", f"/assets/{aid}/complete", {})
    print(f"uploaded {filename} -> {aid}", file=sys.stderr)
    return aid


def submit(engine, mode="emu", params=None, input_files=None):
    body = {"mode": mode, "params": params or {}}
    if input_files:
        body["input_files"] = input_files
    r = api("POST", f"/engines/{engine}/process", body)
    jid = r.get("job_id")
    print(f"{engine} [{mode}] -> {jid or r}", file=sys.stderr)
    return jid, r


def wait(jid, poll=15, tries=40):
    for _ in range(tries):
        s = api("GET", f"/jobs/{jid}/status")
        st = s.get("status")
        if st in ("completed", "failed", "error"):
            return s
        time.sleep(poll)
    return s


def result(jid):
    return api("GET", f"/jobs/{jid}/result")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "upload":
        print(upload(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "image/png"))
    elif cmd == "submit":
        kw = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
        print(submit(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "emu", **kw))
    elif cmd == "status":
        print(json.dumps(api("GET", f"/jobs/{sys.argv[2]}/status"), indent=1))
    elif cmd == "result":
        print(json.dumps(result(sys.argv[2]), indent=1)[:4000])
