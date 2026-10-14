#!/usr/bin/env python3
"""Push current HEAD tree to GitHub via Git Data API (when git HTTPS is blocked)."""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = os.environ.get("GITHUB_REPO", "enternalna-Koh/ReviewAgent")


def run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True, encoding="utf-8", errors="replace").strip()


def gh_api(method: str, path: str, data=None):
    cmd = ["gh", "api", "-X", method, path]
    if data is not None:
        raw = json.dumps(data).encode("utf-8")
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(raw)
            tmp = f.name
        try:
            cmd += ["--input", tmp]
            out = subprocess.check_output(cmd, stderr=subprocess.PIPE)
        finally:
            os.unlink(tmp)
    else:
        out = subprocess.check_output(cmd, stderr=subprocess.PIPE)
    return json.loads(out.decode("utf-8"))


def main() -> int:
    print("Resolving remote main…", flush=True)
    ref = gh_api("GET", f"repos/{REPO}/git/ref/heads/main")
    parent = ref["object"]["sha"]
    print("parent", parent, flush=True)

    lines = run(["git", "ls-tree", "-r", "HEAD"]).splitlines()
    entries = []
    for line in lines:
        meta, path = line.split("\t", 1)
        mode, typ, _sha = meta.split()
        if typ != "blob":
            continue
        entries.append((path, mode))
    print(f"blobs to upload: {len(entries)}", flush=True)

    blob_map = {}
    for i, (path, mode) in enumerate(entries, 1):
        content = subprocess.check_output(["git", "show", f"HEAD:{path}"])
        if len(content) > 500_000:
            payload = {
                "content": base64.b64encode(content).decode("ascii"),
                "encoding": "base64",
            }
        else:
            try:
                payload = {"content": content.decode("utf-8"), "encoding": "utf-8"}
            except UnicodeDecodeError:
                payload = {
                    "content": base64.b64encode(content).decode("ascii"),
                    "encoding": "base64",
                }
        blob = None
        for attempt in range(5):
            try:
                blob = gh_api("POST", f"repos/{REPO}/git/blobs", payload)
                break
            except subprocess.CalledProcessError as e:
                err = e.stderr.decode("utf-8", "replace") if e.stderr else str(e)
                if attempt == 4:
                    print("FAIL blob", path, err[:400], file=sys.stderr)
                    return 1
                time.sleep(1.5 * (attempt + 1))
        assert blob is not None
        blob_map[path] = (mode, blob["sha"])
        if i % 10 == 0 or i == len(entries):
            print(f"  uploaded {i}/{len(entries)}: {path}", flush=True)

    def nest(paths):
        root: dict = {}
        for path, meta in paths.items():
            parts = path.split("/")
            cur = root
            for p in parts[:-1]:
                cur = cur.setdefault(p, {})
            cur[parts[-1]] = {"__file__": meta}
        return root

    tree_root = nest(blob_map)

    def create_tree(node: dict) -> str:
        tree_items = []
        for name, val in sorted(node.items()):
            if isinstance(val, dict) and "__file__" in val:
                mode, sha = val["__file__"]
                tree_items.append(
                    {"path": name, "mode": mode, "type": "blob", "sha": sha}
                )
            else:
                sub_sha = create_tree(val)
                tree_items.append(
                    {"path": name, "mode": "040000", "type": "tree", "sha": sub_sha}
                )
        resp = gh_api("POST", f"repos/{REPO}/git/trees", {"tree": tree_items})
        return resp["sha"]

    print("Creating trees…", flush=True)
    tree_sha = create_tree(tree_root)
    print("tree", tree_sha, flush=True)

    msg = (
        "Ship CLI stack, dual-agent routing, and MindSpore knowledge (API push).\n\n"
        "Includes cann-op-checker / cann-inference-advisor routing, ascend_cli, "
        "tests, and synced skills.\n"
        "Pushed via Git Data API because git HTTPS to github.com:443 is unreachable "
        "from this host.\n"
    )
    commit = gh_api(
        "POST",
        f"repos/{REPO}/git/commits",
        {"message": msg, "tree": tree_sha, "parents": [parent]},
    )
    print("commit", commit["sha"], flush=True)
    gh_api(
        "PATCH",
        f"repos/{REPO}/git/refs/heads/main",
        {"sha": commit["sha"], "force": False},
    )
    print("updated main ->", commit["sha"], flush=True)
    print(f"URL: https://github.com/{REPO}/commit/{commit['sha']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
