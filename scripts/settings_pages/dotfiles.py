import os
import subprocess

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

import dotconfig

from .common import (HOME, ItemList, Page, button, confirm, dialog, in_background, in_terminal, label, load_theme,
                      row, value_row)

REPO = dotconfig.DOTFILES
STATUS = {"M": "changed", "A": "added", "D": "deleted", "R": "renamed", "??": "new", "UU": "conflict"}


def git(*args, timeout=60):
    """(ok, output) of a git command in the dotfiles repo. Never prompts for passwords."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=10")
    try:
        p = subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True, timeout=timeout, env=env)
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


class DotfilesPage(Page):
    """What changed in ~/dotfiles, and committing, pulling and pushing it."""
    name = "dotfiles"

    def __init__(self, panel):
        super().__init__(panel)
        self.busy = False
        self.changes = []
        line, self.branch = value_row("branch")
        line2, self.sync = value_row("sync")
        line3, self.last = value_row("last commit")
        self.add(line, line2, line3)
        self.add(row("", button("pull", lambda: self.action("pulling...", "pull", "--ff-only")),
                     button("push", lambda: self.action("pushing...", "push")),
                     button("open in terminal", lambda: in_terminal("dotfiles", f"cd {REPO} && git status && exec $SHELL", keep_open=False))))

        self.section("changes")
        self.list = ItemList(self.show_diff, empty="nothing to commit")
        self.add(self.list)
        self.message = Gtk.Entry(placeholder_text="what changed?", hexpand=True)
        self.message.connect("activate", lambda _e: self.commit())
        self.commit_button = button("commit all", self.commit)
        self.add(row("", self.message, self.commit_button))
        self.status = label("", "dim", "row", wrap=True)
        self.add(self.status)
        self.add(label(f"repository: {REPO.replace(HOME, '~')} · backups and unsaved settings are git-ignored",
                       "dim", "row", wrap=True))

    def shown(self):
        self.refresh()
        # check the remote in the background, then show ahead/behind again
        in_background(lambda: git("fetch", "--quiet", timeout=30), lambda _r: self.refresh())

    def refresh(self):
        in_background(self._read, self._update)

    @staticmethod
    def _read():
        _ok, branch = git("rev-parse", "--abbrev-ref", "HEAD")
        _ok, counts = git("rev-list", "--left-right", "--count", "HEAD...@{upstream}")
        _ok, last = git("log", "-1", "--format=%s · %cr")
        _ok, porcelain = git("status", "--porcelain=v1", "--untracked-files=all")
        return branch, counts, last, porcelain

    def _update(self, result):
        if isinstance(result, Exception):
            self.status.set_label(str(result))
            return
        branch, counts, last, porcelain = result
        self.branch.set_label(branch)
        try:
            ahead, behind = (int(n) for n in counts.split())
            parts = ([f"{ahead} to push"] if ahead else []) + ([f"{behind} to pull"] if behind else [])
            self.sync.set_label(" · ".join(parts) or "up to date")
        except ValueError:
            self.sync.set_label("no upstream branch")
        self.last.set_label(last)
        self.changes = []
        for line in porcelain.splitlines():
            code, path = line[:2].strip(), line[3:]
            self.changes.append((path, code))
        self.list.set_items((path, path, STATUS.get(code, STATUS.get(code[:1], code)), False)
                            for path, code in self.changes)
        self.commit_button.set_sensitive(bool(self.changes) and not self.busy)

    def show_diff(self, path):
        code = dict(self.changes).get(path, "")
        if code == "??":
            text = dotconfig.read(os.path.join(REPO, path))
            text = "".join(f"+{l}\n" for l in text.splitlines()) or "(empty or binary file)\n"
        else:
            _ok, text = git("diff", "HEAD", "--", path)
        view = Gtk.TextView(editable=False, monospace=True, css_classes=["diff"], left_margin=12, right_margin=12,
                            top_margin=8, bottom_margin=8)
        buffer = view.get_buffer()
        theme = load_theme()
        tags = {"+": buffer.create_tag(foreground=theme["accent"]), "-": buffer.create_tag(foreground=theme["c1"]),
                "@": buffer.create_tag(foreground=theme["dim"])}
        for line in (text or "no changes\n").splitlines(True):
            tag = tags["@"] if line.startswith(("+++", "---", "diff ", "index ")) else tags.get(line[:1])
            if not line.endswith("\n"):
                line += "\n"
            if tag:
                buffer.insert_with_tags(buffer.get_end_iter(), line, tag)
            else:
                buffer.insert(buffer.get_end_iter(), line)
        buttons = [("close", None)]
        if code != "??":
            buttons.insert(0, ("undo these changes", "revert"))
        dialog(self.panel, path, Gtk.ScrolledWindow(child=view, min_content_height=380), buttons,
               lambda r: r == "revert" and self.revert(path), width=760, height=520)

    def revert(self, path):
        confirm(self.panel, "undo changes", f"Put {path} back the way it was in the last commit?", "undo",
                lambda: self.action(f"undoing {path}...", "checkout", "HEAD", "--", path))

    def commit(self):
        message = self.message.get_text().strip()
        if not self.changes:
            return
        if not message:
            self.status.set_label("write a short message about what changed first")
            self.message.grab_focus()
            return

        def work():
            ok, output = git("add", "-A")
            if ok:
                ok, output = git("commit", "-m", message)
            return ok, output

        self.run(f"committing {len(self.changes)} file{'s' if len(self.changes) != 1 else ''}...", work,
                 lambda: self.message.set_text(""))

    def action(self, text, *args):
        self.run(text, lambda: git(*args, timeout=120))

    def run(self, text, work, on_success=None):
        if self.busy:
            return
        self.busy = True
        self.status.set_label(text)

        def done(result):
            self.busy = False
            ok, output = result if not isinstance(result, Exception) else (False, str(result))
            last_line = output.strip().splitlines()[-1] if output.strip() else ""
            if ok:
                self.status.set_label(last_line or "done")
                if on_success:
                    on_success()
            elif "permission denied" in output.lower() or "could not read" in output.lower():
                self.status.set_label("git couldn't sign in; use open in terminal to push or pull with your key")
            else:
                self.status.set_label(f"failed: {last_line}")
            self.refresh()

        in_background(work, done)
