#!/usr/bin/env python3
"""Local agent usage for Waybar and the shared, pywal-themed fuzzel menu.

Totals cover retained local history, not billing statements. Codex quotas are
session snapshots; Claude quotas use its account /usage endpoint and local login.
"""
import argparse
from datetime import datetime
import fcntl
import html
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import math
import urllib.request
import urllib.error
import time

HOME = Path.home()
CODEX = Path(os.environ.get("CODEX_HOME", HOME / ".codex"))
CLAUDE = Path(os.environ.get("CLAUDE_CONFIG_DIR", HOME / ".claude"))
DATA = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share"))
CACHE = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / "agent-usage"
NAMES = ("codex", "claude code", "opencode")


def number(value):
    return max(0, value) if isinstance(value, (int, float)) else 0


def stamp(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError, TypeError):
        return 0


def empty():
    return dict(input=0, output=0, cache_read=0, cache_write=0,
                sessions=0, updated=0, quota=None, cost=None)


def records(path):
    with path.open(errors="replace") as source:
        for line in source:
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    yield value
            except ValueError:
                # A running agent can leave a partial final record.
                continue


def codex_file(path):
    result = empty()
    for record in records(path):
        payload = record.get("payload") or {}
        if record.get("type") == "session_meta":
            result["session_id"] = payload.get("id", str(path))
        if record.get("type") != "event_msg" or payload.get("type") != "token_count":
            continue
        when = stamp(record.get("timestamp"))
        info = payload.get("info") or {}
        usage = info.get("total_token_usage") or {}
        if usage:
            # Codex input includes cached input; keep categories disjoint.
            cached = number(usage.get("cached_input_tokens"))
            result["input"] = max(result["input"], number(usage.get("input_tokens")) - cached)
            result["cache_read"] = max(result["cache_read"], cached)
            result["output"] = max(result["output"], number(usage.get("output_tokens")))
            result["sessions"] = 1
            result["updated"] = max(result["updated"], when)
        limits = payload.get("rate_limits")
        if limits and limits.get("limit_id") in (None, "codex"):
            if when >= (result.get("quota") or {}).get("timestamp", 0):
                result["quota"] = {"timestamp": when, "limits": limits}
    return result


def claude_file(path):
    result = empty()
    messages = {}
    for record in records(path):
        message = record.get("message")
        if record.get("type") != "assistant" or not isinstance(message, dict):
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        # Streaming content blocks repeat usage for the same API message.
        key = message.get("id") or record.get("uuid")
        if not key:
            continue
        previous = messages.setdefault(key, {})
        for field in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            previous[field] = max(previous.get(field, 0), number(usage.get(field)))
        result["updated"] = max(result["updated"], stamp(record.get("timestamp")))
    result["messages"] = messages
    result["sessions"] = int(bool(messages))
    return result


def log_usage(roots, parser, old, new):
    result = empty()
    sessions = {}
    messages = {}
    for root in roots:
        for path in root.rglob("*.jsonl"):
            stat = path.stat()
            key = str(path)
            signature = [stat.st_mtime_ns, stat.st_size]
            saved = old.get(key, {})
            if saved.get("signature") == signature:
                value = saved["value"]
            else:
                value = parser(path)
            new[key] = {"signature": signature, "value": value}
            # Archived copies of a Codex session count once.
            session = value.get("session_id", key)
            if session not in sessions or value["updated"] >= sessions[session]["updated"]:
                sessions[session] = value
    for value in sessions.values():
        for field in ("input", "output", "cache_read", "cache_write", "sessions"):
            result[field] += value[field]
        result["updated"] = max(result["updated"], value["updated"])
        quota = value.get("quota")
        if quota and quota["timestamp"] >= (result.get("quota") or {}).get("timestamp", 0):
            result["quota"] = quota
        for key, usage in value.get("messages", {}).items():
            prev = messages.setdefault(key, {})
            for field, amount in usage.items():
                prev[field] = max(prev.get(field, 0), amount)
    for usage in messages.values():
        for source, target in (("input_tokens", "input"), ("output_tokens", "output"),
                               ("cache_read_input_tokens", "cache_read"), ("cache_creation_input_tokens", "cache_write")):
            result[target] += usage.get(source, 0)
    return result


def opencode_usage():
    result = empty()
    path = DATA / "opencode/opencode.db"
    if not path.is_file():
        return result
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)
    try:
        row = connection.execute("""SELECT count(*), sum(tokens_input), sum(tokens_output),
            sum(tokens_cache_read), sum(tokens_cache_write), sum(cost), max(time_updated)
            FROM session""").fetchone()
        for field, value in zip(("sessions", "input", "output", "cache_read", "cache_write", "cost", "updated"), row):
            result[field] = number(value)
        result["updated"] /= 1000
        # A fresh empty database has no recorded cost, rather than a bill of $0.
        if not result["sessions"]:
            result["cost"] = None
    finally:
        connection.close()
    return result


def collect(force=False):
    CACHE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (CACHE / "collect.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = CACHE / "usage.json"
        try:
            saved = json.loads(path.read_text())
        except (OSError, ValueError):
            saved = {}
        if not force and time.time() - saved.get("timestamp", 0) < 20:
            return with_claude_quota(saved["providers"])
        old = saved.get("files", {})
        files = {}
        providers = {}
        for name, reader in (
            ("codex", lambda: log_usage([CODEX / "sessions", CODEX / "archived_sessions"], codex_file, old, files)),
            ("claude code", lambda: log_usage([CLAUDE / "projects"], claude_file, old, files)),
            ("opencode", opencode_usage),
        ):
            try:
                providers[name] = reader()
            except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as error:
                providers[name] = empty()
                providers[name]["error"] = f"usage unavailable ({type(error).__name__})"
        temporary = CACHE / "usage.tmp"
        temporary.write_text(json.dumps(dict(timestamp=time.time(), providers=providers, files=files)))
        temporary.chmod(0o600)
        temporary.replace(path)
        return with_claude_quota(providers, force=force)


def claude_account_snapshot(data):
    """The /usage endpoint reports utilization in percent, not a fraction."""
    limits = {}
    for source, target, minutes in (("five_hour", "primary", 300), ("seven_day", "secondary", 10080)):
        window = data.get(source)
        if not isinstance(window, dict):
            continue
        used = window.get("utilization")
        reset = stamp(window.get("resets_at"))
        if isinstance(used, (int, float)) and math.isfinite(used) and reset:
            limits[target] = dict(used_percent=used, resets_at=reset, window_minutes=minutes)
    return dict(timestamp=time.time(), limits=limits, source="Claude account /usage")


def with_claude_quota(providers, force=False):
    path = CACHE / "claude-account-usage.json"
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        saved = {}
    interval = 15 if force else 300 if saved.get("error") else 120
    if time.time() - saved.get("checked", 0) >= interval:
        error = None
        try:
            credentials = json.loads((CLAUDE / ".credentials.json").read_text())
            token = credentials.get("claudeAiOauth", {}).get("accessToken")
            if not token:
                raise ValueError("no OAuth login")
            # Exactly the account endpoint used by the installed Claude /usage command.
            request = urllib.request.Request("https://api.anthropic.com/api/oauth/usage", headers={
                "Authorization": "Bearer " + token,
                "anthropic-beta": "oauth-2025-04-20",
                "User-Agent": "dotfiles-agent-usage/1.0",
            })
            with urllib.request.urlopen(request, timeout=5) as response:
                data = json.load(response)
            saved["snapshot"] = claude_account_snapshot(data)
        except urllib.error.HTTPError as exc:
            error = "login expired; sign in with Claude" if exc.code in (401, 403) else f"account refresh failed (HTTP {exc.code})"
        except (OSError, ValueError, AttributeError, TypeError):
            error = "account refresh unavailable; check Claude login/network"
        saved.update(checked=time.time(), error=error)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(saved))
        temporary.chmod(0o600)
        temporary.replace(path)
    providers["claude code"]["quota"] = saved.get("snapshot")
    providers["claude code"]["quota_error"] = saved.get("error")
    return providers


def compact(value):
    for scale, suffix in ((1e9, "b"), (1e6, "m"), (1e3, "k")):
        if value >= scale:
            return f"{value / scale:.1f}{suffix}"
    return str(int(value))


def total(value):
    return sum(value[field] for field in ("input", "output", "cache_read", "cache_write"))


def local_time(value):
    return datetime.fromtimestamp(value).astimezone().strftime("%b %d %-I:%M %p") if value else "unknown"


def quotas(value):
    snapshot = value.get("quota")
    if not snapshot:
        return []
    rows = []
    for name in ("primary", "secondary"):
        window = snapshot["limits"].get(name)
        if not isinstance(window, dict) or not isinstance(window.get("used_percent"), (int, float)):
            continue
        minutes = number(window.get("window_minutes"))
        label = f"{minutes / 1440:g}d" if minutes >= 1440 else f"{minutes / 60:g}h"
        reset = number(window.get("resets_at"))
        left = max(0, min(100, 100 - window["used_percent"]))
        if reset and reset <= time.time():
            rows.append(f"{label} quota · snapshot expired; use the agent to update")
        else:
            rows.append(f"{label} quota · {left:g}% left · resets {local_time(reset)}")
    return rows


def summary(name, value):
    if value.get("error"):
        return f"{name} · {value['error']}"
    if not value["sessions"]:
        return f"{name} · no local usage yet"
    return f"{name} · {compact(total(value))} tokens"


def details(name, value):
    rows = [summary(name, value), "retained local history · all time (includes cached tokens)"]
    if value["sessions"]:
        rows += [f"input · {value['input']:,}", f"output · {value['output']:,}",
                 f"cache read · {value['cache_read']:,}", f"cache write · {value['cache_write']:,}",
                 f"last usage · {local_time(value['updated'])}"]
    rows.append(f"recorded cost · ${value['cost']:.4f} (not a bill)" if value["cost"] is not None
                else "cost · not recorded locally")
    rows += quotas(value) or (["quota · account usage unavailable"] if name == "claude code"
                             else ["quota · not available in local history"])
    if value.get("quota_error"):
        rows.append(value["quota_error"] + " · last snapshot may be stale")
    if value.get("quota"):
        rows.append(f"source · {value['quota'].get('source', 'Codex session history')}")
        rows.append(f"quota snapshot · {local_time(value['quota']['timestamp'])}")
    return rows


def bar(providers):
    tooltip = []
    for name in NAMES:
        value = providers[name]
        tooltip.append(summary(name, value))
        tooltip.extend(quotas(value))
        if value.get("quota_error"):
            tooltip.append("account refresh failed · showing last snapshot")
    tooltip.append("click for usage · right-click to refresh account limits")
    print(json.dumps({"text": "󰚩", "tooltip": html.escape("\n".join(tooltip)), "class": "agents"}))


def choose(rows, prompt):
    result = subprocess.run(["fuzzel", "--dmenu", "--index", "--prompt", f"{prompt} > ",
                             "--minimal-lines", "--lines", "10", "--width", "40"],
                            input="\n".join(rows), text=True, capture_output=True)
    selected = result.stdout.strip()
    return int(selected) if result.returncode == 0 and selected.isdigit() and int(selected) < len(rows) else None


def refresh_bar():
    subprocess.run(["pkill", f"-{signal.SIGRTMIN + 12}", "-x", "waybar"], capture_output=True)


def menu():
    CACHE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (CACHE / "menu.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        current = None
        while True:
            providers = collect()
            if current is None:
                rows = [summary(name, providers[name]) for name in NAMES] + ["refresh", "copy summary"]
            else:
                rows = ["back", "refresh", "copy details"] + details(current, providers[current])
            selected = choose(rows, current or "agents")
            if selected is None:
                return
            if current is None and selected < 3:
                current = NAMES[selected]
            elif current is not None and selected == 0:
                current = None
            elif (current is None and selected == 3) or (current is not None and selected == 1):
                collect(force=True)
                refresh_bar()
            elif (current is None and selected == 4) or (current is not None and selected == 2):
                text = "\n".join(details(current, providers[current])) if current else "\n\n".join(
                    "\n".join(details(name, providers[name])) for name in NAMES)
                subprocess.run(["wl-copy"], input=text, text=True, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("bar", "menu", "json", "refresh"), nargs="?", default="bar")
    args = parser.parse_args()
    if args.mode == "menu":
        menu()
    else:
        providers = collect(force=args.mode == "refresh")
        if args.mode == "json":
            print(json.dumps(providers, indent=2))
        else:
            bar(providers)
        if args.mode == "refresh":
            refresh_bar()
