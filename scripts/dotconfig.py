"""Staged config changes and backups for the settings panel and wallpaper picker.

Sway changes are written to ~/.config/sway/settings.conf, which the main config includes near
its end, so they apply live (and survive reloads) without touching the config itself. Saving
merges them into the matching lines of ~/.config/sway/config, after checking the result with
`sway -C` and backing the old config up. Discarding empties settings.conf.

Other files (the waybar config template, for example) are staged as whole new contents under
~/.cache/settings-panel/pending and written, with a backup, on save.

Backups live in ~/dotfiles/backups/<path under ~>/<timestamp>, the last 10 per file.
"""
import difflib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time

HOME = os.path.expanduser("~")
DOTFILES = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
BACKUPS = os.path.join(DOTFILES, "backups")
KEEP_BACKUPS = 10
SWAY_CONFIG = os.path.join(HOME, ".config/sway/config")
SWAY_PENDING = os.path.join(HOME, ".config/sway/settings.conf")
INCLUDE_LINE = "include ~/.config/sway/settings.conf"
FILE_PENDING = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.join(HOME, ".cache"),
                            "settings-panel", "pending")
PENDING_HEADER = ("# Unsaved changes from the settings panel. Save or discard them there;\n"
                  "# saving merges them into ~/.config/sway/config.\n")


def read(path, default=""):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return default


def write_atomic(path, text):
    path = os.path.realpath(path)  # write through stow's symlinks into the repo
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".settings-")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        try:
            os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        except FileNotFoundError:
            os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def run(*cmd, timeout=10):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode == 0, (p.stdout + p.stderr).strip()
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)


###############
### BACKUPS ###
###############


def _backup_dir(path):
    path = os.path.abspath(os.path.expanduser(path))
    relative = os.path.relpath(path, HOME) if path.startswith(HOME + "/") else path.lstrip("/")
    return os.path.join(BACKUPS, relative)


def backup(path):
    """Copy path's current contents into the backups, keeping the newest KEEP_BACKUPS. Returns the copy."""
    source = os.path.realpath(os.path.expanduser(path))
    if not os.path.isfile(source):
        return None
    folder = _backup_dir(path)
    os.makedirs(folder, exist_ok=True)
    name = time.strftime("%Y-%m-%d_%H-%M-%S")
    dest = os.path.join(folder, name)
    n = 1
    while os.path.exists(dest):
        n += 1
        dest = os.path.join(folder, f"{name}_{n}")
    shutil.copy2(source, dest)
    for old in list_backups(path)[KEEP_BACKUPS:]:
        try:
            os.remove(old["backup"])
        except OSError:
            pass
    return dest


def list_backups(path):
    """Newest first: [{backup, time, size}]."""
    folder = _backup_dir(path)
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    entries = []
    for name in names:
        full = os.path.join(folder, name)
        if os.path.isfile(full):
            stat = os.stat(full)
            entries.append({"backup": full, "time": stat.st_mtime, "size": stat.st_size, "name": name})
    return sorted(entries, key=lambda e: e["time"], reverse=True)


def backed_up_files():
    """Every file that has backups, as paths under ~."""
    found = []
    for root, _dirs, files in os.walk(BACKUPS):
        if files:
            relative = os.path.relpath(root, BACKUPS)
            found.append(os.path.join(HOME, relative))
    return sorted(found)


def restore(path, backup_path):
    """Put a backup back (backing up the current version first)."""
    backup(path)
    write_atomic(os.path.expanduser(path), read(backup_path))


def diff(old, new, name="config"):
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                        f"{name} (saved)", f"{name} (with changes)", n=1))


############
### SWAY ###
############


def _tokens(line):
    return re.findall(r'"[^"]*"|\'[^\']*\'|\S+', line.strip())


def sway_key(line):
    """What a sway directive sets, so a newer line can replace an older one. None for comments."""
    tokens = _tokens(line)
    if not tokens or tokens[0].startswith("#"):
        return None
    head = tokens[0]
    if head in ("bindsym", "bindcode", "unbindsym", "unbindcode"):
        rest = [t for t in tokens[1:] if not t.startswith("--")]
        return f"{head.removeprefix('un')} {rest[0].lower()}" if rest else None
    if head == "for_window":
        match = re.match(r"\s*for_window\s+(\[.*?\])", line)
        return f"for_window {match.group(1)}" if match else None
    if head in ("bindgesture", "unbindgesture"):
        rest = [t for t in tokens[1:] if not t.startswith("--")]
        return f"bindgesture {rest[0].lower()}" if rest else None
    if head in ("input", "seat") and len(tokens) >= 3:
        return f"{head} {tokens[1]} {tokens[2]}"
    if head == "output" and len(tokens) >= 3:
        return f"output {tokens[1]} {tokens[2]}"
    if head in ("set", "gaps", "smart_gaps", "hide_edge_borders") and len(tokens) >= 2:
        return f"{head} {tokens[1]}" if head in ("set", "gaps") else head
    if head.startswith("client.") or head.startswith("exec"):
        return head if head.startswith("client.") else None
    return head


def sway_pending():
    """{key: line} of the staged sway changes, in order."""
    pending = {}
    for line in read(SWAY_PENDING).splitlines():
        key = sway_key(line)
        if key:
            pending[key] = line.strip()
    return pending


def _write_pending(pending):
    body = "\n".join(pending.values())
    write_atomic(SWAY_PENDING, PENDING_HEADER + (body + "\n" if body else ""))


def stage_sway(*lines, reload=True):
    """Stage sway directives (replacing staged ones that set the same thing) and apply them."""
    pending = sway_pending()
    for line in lines:
        key = sway_key(line)
        if key:
            pending.pop(key, None)
            if sway_config_line(key) != line.strip():
                pending[key] = line.strip()
    _write_pending(pending)
    return reload_sway() if reload else (True, "")


def unstage_sway(key, reload=True):
    pending = sway_pending()
    if pending.pop(key, None) is not None:
        _write_pending(pending)
        if reload:
            reload_sway()


def reload_sway():
    return run("swaymsg", "reload")


def _blocks(lines):
    """(index, depth, block header) for each line of a sway config."""
    depth, stack, out = 0, [], []
    for index, line in enumerate(lines):
        stripped = line.split("#", 1)[0].strip() if not line.strip().startswith("#") else ""
        out.append((index, depth, stack[-1] if stack else None))
        if stripped.endswith("{"):
            stack.append(stripped[:-1].strip())
            depth += 1
        elif stripped == "}" and depth:
            stack.pop()
            depth -= 1
    return out


def sway_config_line(key, config=None):
    """The main config's current line for key (block properties come back as one-line directives)."""
    lines = (read(SWAY_CONFIG) if config is None else config).splitlines()
    found = None
    for index, depth, block in _blocks(lines):
        line = lines[index].strip()
        if not line or line.startswith("#"):
            continue
        if depth == 0 and sway_key(line) == key:
            found = line
        elif depth == 1 and block and block.split()[0] in ("input", "seat", "output"):
            if sway_key(f"{block} {line}") == key:
                found = f"{block} {line}"
    return found


def sway_value(key):
    """The effective line for key: staged if there is one, otherwise the saved config's."""
    return sway_pending().get(key) or sway_config_line(key)


def merge_sway(config, pending):
    """The config with the staged lines merged in: replaced in place, or added above the include."""
    lines = config.splitlines()
    for key, new in pending.items():
        tokens = _tokens(new)
        # unbind*, or a window rule staged as "nop" (sway has no way to delete one live)
        remove = tokens[0].startswith("un") or (tokens[0] == "for_window" and new.rstrip().endswith("] nop"))
        block_head = f"{tokens[0]} {tokens[1]}" if tokens[0] in ("input", "seat", "output") else None
        replaced = False
        info = _blocks(lines)
        for index, depth, block in reversed(info):
            line = lines[index].strip()
            if not line or line.startswith("#"):
                continue
            indent = lines[index][:len(lines[index]) - len(lines[index].lstrip())]
            if depth == 0 and sway_key(line) == key:
                if remove:
                    del lines[index]
                else:
                    lines[index] = indent + new
                replaced = True
                break
            if depth == 1 and block and block_head and block == block_head and sway_key(f"{block} {line}") == key:
                lines[index] = indent + " ".join(tokens[2:])
                replaced = True
                break
        if replaced or remove:
            continue
        if block_head:
            # add the property to an existing block if there is one
            info = _blocks(lines)
            opener = next((i for i, d, _b in info if d == 0 and lines[i].strip().rstrip("{").strip() == block_head
                           and lines[i].strip().endswith("{")), None)
            if opener is not None:
                close = next(i for i, d, _b in info if i > opener and d == 1 and lines[i].strip() == "}")
                lines.insert(close, "    " + " ".join(tokens[2:]))
                continue
        at = next((i for i, l in enumerate(lines) if l.strip() == INCLUDE_LINE), len(lines))
        while at > 0 and lines[at - 1].strip().startswith("#"):
            at -= 1  # above the include's comment, not between it and the include
        lines.insert(at, new)
    return "\n".join(lines) + "\n"


def check_sway(config_text):
    """Validate a whole config with `sway -C`. Returns (ok, message)."""
    folder = os.path.dirname(os.path.realpath(SWAY_CONFIG))
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".check-")
    try:
        with os.fdopen(fd, "w") as f:
            # the check must not pull in the staged file again
            f.write(config_text.replace(INCLUDE_LINE, "# " + INCLUDE_LINE))
        ok, output = run("sway", "-C", "-c", tmp, timeout=20)
        errors = [re.sub(r"^[\d:.]+ \[ERROR\] \[[^\]]*\] ", "", l) for l in output.splitlines()
                  if "[ERROR]" in l and "Error(s) loading config" not in l]
        return ok, (errors[0] if errors else output.splitlines()[-1] if output else "")
    finally:
        os.unlink(tmp)


def sway_diff():
    config = read(SWAY_CONFIG)
    return diff(config, merge_sway(config, sway_pending()), "sway/config")


def save_sway():
    """Merge staged changes into the config. Returns (ok, message)."""
    pending = sway_pending()
    if not pending:
        return True, "nothing to save"
    config = read(SWAY_CONFIG)
    merged = merge_sway(config, pending)
    ok, message = check_sway(merged)
    if not ok:
        return False, f"sway rejected the result: {message}"
    backup(SWAY_CONFIG)
    write_atomic(SWAY_CONFIG, merged)
    _write_pending({})
    reload_sway()
    return True, f"saved {len(pending)} change{'s' if len(pending) != 1 else ''}"


def discard_sway():
    _write_pending({})
    reload_sway()


#############
### FILES ###
#############


def _pending_path(path):
    return os.path.join(FILE_PENDING, re.sub(r"[^A-Za-z0-9_.-]", "_", os.path.relpath(path, HOME)) + ".json")


def stage_file(path, content, label, apply=None):
    """Stage new contents for a file. apply: a shell command run after saving (and after discarding)."""
    path = os.path.expanduser(path)
    if read(path) == content:
        unstage_file(path)
        return
    os.makedirs(FILE_PENDING, exist_ok=True)
    write_atomic(_pending_path(path), json.dumps({"path": path, "content": content, "label": label, "apply": apply}))


def unstage_file(path):
    try:
        os.remove(_pending_path(os.path.expanduser(path)))
    except FileNotFoundError:
        pass


def files_pending():
    try:
        names = sorted(os.listdir(FILE_PENDING))
    except OSError:
        return []
    items = []
    for name in names:
        try:
            with open(os.path.join(FILE_PENDING, name)) as f:
                items.append(json.load(f))
        except (OSError, ValueError):
            pass
    return items


def file_pending_content(path):
    path = os.path.expanduser(path)
    return next((item["content"] for item in files_pending() if item["path"] == path), None)


###########
### ALL ###
###########


def pending_count():
    return len(sway_pending()) + len(files_pending())


def pending_summary():
    """Readable lines describing every staged change."""
    lines = [f"sway: {line}" for line in sway_pending().values()]
    lines += [f"{item['label']}: {os.path.relpath(item['path'], HOME)}" for item in files_pending()]
    return lines


def full_diff():
    parts = [sway_diff()] if sway_pending() else []
    for item in files_pending():
        parts.append(diff(read(item["path"]), item["content"], os.path.relpath(item["path"], HOME)))
    return "\n".join(parts)


def save_all():
    ok, message = save_sway()
    if not ok:
        return False, message
    for item in files_pending():
        try:
            backup(item["path"])
            write_atomic(item["path"], item["content"])
        except OSError as e:
            return False, f"couldn't write {item['path']}: {e.strerror}"
        unstage_file(item["path"])
        if item.get("apply"):
            subprocess.Popen(["sh", "-c", item["apply"]], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True, "saved"


def discard_all():
    items = files_pending()
    for item in items:
        unstage_file(item["path"])
        if item.get("apply"):
            subprocess.Popen(["sh", "-c", item["apply"]], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    discard_sway()
