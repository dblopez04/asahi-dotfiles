import os
import shutil

from .common import Page, button, confirm, human_size, in_background, in_terminal, label, row, run

TASKS = [
    # (section, title, subtitle, command, needs a terminal, size probe)
    ("updates", "system packages", "dnf upgrade", "sudo dnf upgrade --refresh", True, None),
    ("updates", "flatpak apps", "flatpak update", "flatpak update", True, None),
    ("updates", "pipx tools", "pipx upgrade-all", "pipx upgrade-all", True, None),
    ("updates", "firmware", "fwupdmgr", "fwupdmgr refresh; fwupdmgr get-updates && fwupdmgr update", True, None),
    ("clean up", "unused packages", "dnf autoremove", "sudo dnf autoremove", True, None),
    ("clean up", "unused flatpak runtimes", "flatpak uninstall --unused", "flatpak uninstall --unused", True, None),
    ("clean up", "package cache", "dnf clean all", "sudo dnf clean all", True, "/var/cache/libdnf5"),
    ("clean up", "thumbnails", "~/.cache/thumbnails", "rm -rf ~/.cache/thumbnails", False, "~/.cache/thumbnails"),
    ("clean up", "app caches", "everything in ~/.cache except the pywal colors",
     "find ~/.cache -mindepth 1 -maxdepth 1 ! -name wal ! -name settings-panel -exec rm -rf {} +", False, "~/.cache"),
    ("clean up", "trash", "~/.local/share/Trash", "gio trash --empty", False, "~/.local/share/Trash"),
    ("clean up", "old logs", "keep two weeks of the system journal", "sudo journalctl --vacuum-time=2weeks", True,
     "/var/log/journal"),
    ("clean up", "containers", "podman system prune", "podman system prune", True, "~/.local/share/containers"),
]


def folder_size(path):
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return 0
    out = run("du", "-sb", path, timeout=120)
    try:
        return int(out.split()[0])
    except (IndexError, ValueError):
        return 0


class MaintenancePage(Page):
    name = "maintenance"

    def __init__(self, panel):
        super().__init__(panel)
        self.sizes = {}
        section = None
        for index, (group, title, sub, command, terminal, probe) in enumerate(TASKS):
            tool = command.split()[1] if command.startswith("sudo") else command.split()[0]
            if not shutil.which(tool) and tool not in ("rm", "find"):
                continue
            if group != section:
                self.section(group)
                section = group
            subtitle = label(sub, "dim")
            if probe:
                self.sizes[index] = subtitle
            self.add(row(title, button("run", lambda i=index: self.start(i)), sub=subtitle))
        self.status = label("", "dim", "row", wrap=True)
        self.add(self.status)

    def shown(self):
        def work():
            return {i: folder_size(TASKS[i][5]) for i in self.sizes}

        in_background(work, self._sizes)

    def _sizes(self, sizes):
        if isinstance(sizes, Exception):
            return
        for index, size in sizes.items():
            if size:
                self.sizes[index].set_label(f"{TASKS[index][2]}  ·  {human_size(size)}")

    def start(self, index):
        _group, title, _sub, command, terminal, _probe = TASKS[index]

        def go():
            if terminal:
                in_terminal(title, command)
                self.status.set_label(f"{title}: running in a terminal")
            else:
                in_background(lambda: run("sh", "-c", command, timeout=300),
                              lambda _r: (self.status.set_label(f"{title}: done"), self.shown()))

        confirm(self.panel, title, f"Run this?\n\n{command}", "run", go)
