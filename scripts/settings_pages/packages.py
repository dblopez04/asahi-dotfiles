import configparser
import os
import re
import shutil

from gi.repository import Gio, Gtk

import dotconfig

from .common import (HOME, V, Choice, ItemList, Page, Toggle, button, confirm, dialog, human_size, in_background,
                      in_terminal, label, quote, row, run, run_json)

LOCAL_APPS = os.path.join(HOME, ".local/share/applications")


def list_dnf(all_packages):
    names = None if all_packages else set(run("dnf", "repoquery", "--userinstalled", "--qf", "%{name}\n",
                                             timeout=120).split())
    items = []
    for line in run("rpm", "-qa", "--qf", "%{NAME}\t%{VERSION}-%{RELEASE}\t%{SIZE}\t%{SUMMARY}\n", timeout=60).splitlines():
        parts = line.split("\t")
        if len(parts) == 4 and (names is None or parts[0] in names):
            items.append({"source": "dnf", "name": parts[0], "version": parts[1],
                          "size": int(parts[2] or 0), "summary": parts[3]})
    return items


def list_flatpak():
    items = []
    for line in run("flatpak", "list", "--app", "--columns=application,name,version,size,installation").splitlines():
        parts = line.split("\t")
        if len(parts) >= 5:
            items.append({"source": "flatpak", "name": parts[0], "version": parts[2], "summary": parts[1],
                          "size_text": parts[3], "installation": parts[4]})
    return items


def list_pipx():
    data = run_json("pipx", "list", "--json", default={})
    return [{"source": "pipx", "name": name, "version": v["metadata"]["main_package"]["package_version"],
             "summary": ", ".join(v["metadata"]["main_package"].get("apps", []))}
            for name, v in (data.get("venvs") or {}).items()]


def list_npm():
    items = []
    for tool, cmd in (("npm", ["npm", "ls", "-g", "--depth=0", "--json"]), ("pnpm", ["pnpm", "ls", "-g", "--json"])):
        if not shutil.which(tool):
            continue
        data = run_json(*cmd, timeout=60, default={})
        data = data[0] if isinstance(data, list) and data else data
        for name, info in ((data or {}).get("dependencies") or {}).items():
            if tool == "npm" and name in ("npm", "corepack"):
                continue
            items.append({"source": tool, "name": name, "version": info.get("version", ""), "summary": "global package"})
    return items


def list_other():
    """Tools installed by their own installers into ~/.local/bin, ~/.cargo/bin, ~/.bun/bin."""
    items = []
    for folder, source in ((os.path.join(HOME, ".cargo/bin"), "cargo"), (os.path.join(HOME, ".bun/bin"), "bun"),
                           (os.path.join(HOME, ".local/bin"), "local")):
        try:
            entries = sorted(os.listdir(folder))
        except OSError:
            continue
        for name in entries:
            path = os.path.join(folder, name)
            real = os.path.realpath(path)
            if source == "local" and (real.startswith(dotconfig.DOTFILES + os.sep) or "pipx" in real):
                continue  # these scripts, and pipx's own links
            if os.access(path, os.X_OK) and not os.path.isdir(path):
                items.append({"source": source, "name": name, "version": "", "summary": real if real != path else "",
                              "size": os.path.getsize(real) if os.path.exists(real) else 0})
    return items


UNINSTALL = {
    "dnf": lambda item: f"sudo dnf remove {quote(item['name'])}",
    "flatpak": lambda item: f"flatpak uninstall {'--user ' if item.get('installation') == 'user' else ''}{quote(item['name'])}",
    "pipx": lambda item: f"pipx uninstall {quote(item['name'])}",
    "npm": lambda item: f"npm rm -g {quote(item['name'])}",
    "pnpm": lambda item: f"pnpm rm -g {quote(item['name'])}",
    "cargo": lambda item: f"cargo uninstall {quote(item['name'])}",
    "bun": lambda item: f"bun rm -g {quote(item['name'])}",
    "local": lambda item: f"rm -i {quote(os.path.join(HOME, '.local/bin', item['name']))}",
}

DESKTOP_FIELDS = [("Name", "name"), ("Comment", "comment"), ("Exec", "command"), ("Icon", "icon"),
                  ("Categories", "categories"), ("Keywords", "keywords")]


class PackagesPage(Page):
    name = "packages & apps"

    def __init__(self, panel):
        super().__init__(panel)
        self.items = []
        self.loaded = False
        self.view = "packages"

        tabs = Gtk.Box(spacing=4, css_classes=["section-row"])
        self.tabs = {}
        for name in ("packages", "applications"):
            tab = Gtk.Button(label=name, css_classes=["tab"])
            tab.connect("clicked", lambda _b, n=name: self.switch(n))
            tabs.append(tab)
            self.tabs[name] = tab
        self.append(tabs)

        self.search = Gtk.SearchEntry(placeholder_text="search", hexpand=True)
        self.search.connect("search-changed", lambda _: self.fill())
        self.source = Choice([("all", "everything"), ("dnf", "dnf"), ("flatpak", "flatpak"), ("pipx", "pipx"),
                              ("npm", "npm / pnpm"), ("other", "other installers")], lambda _v: self.fill())
        self.source.set_value("all")
        self.all_dnf = Toggle(lambda _on: self.load())
        self.filters = Gtk.Box(orientation=V)
        self.filters.append(row("", self.search, self.source))
        self.filters.append(row("include dnf dependencies", self.all_dnf))
        self.status = label("", "dim", "row")
        self.append(self.filters)
        self.append(self.status)

        self.detail = Gtk.Box(orientation=V, css_classes=["row"], visible=False)
        self.append(self.detail)
        self.list = ItemList(self.select, empty="loading...")
        self.append(self.list)
        self.switch("packages")

    def shown(self):
        if not self.loaded:
            self.load()

    # ----- packages -----

    def load(self):
        self.loaded = True
        self.status.set_label("reading installed packages...")
        everything = self.all_dnf.active

        def work():
            items = []
            for reader in (lambda: list_dnf(everything), list_flatpak, list_pipx, list_npm, list_other):
                try:
                    items += reader()
                except Exception:
                    pass
            return items

        in_background(work, self._loaded)

    def _loaded(self, items):
        self.items = sorted(items, key=lambda i: i["name"].lower()) if isinstance(items, list) else []
        self.fill()

    def switch(self, view):
        self.view = view
        for name, tab in self.tabs.items():
            (tab.add_css_class if name == view else tab.remove_css_class)("on")
        self.source.set_visible(view == "packages")
        self.all_dnf.get_parent().set_visible(view == "packages")
        self.detail.set_visible(False)
        if view == "applications":
            self.list.on_activate = self.edit_app
        else:
            self.list.on_activate = self.select
        self.fill()

    def fill(self):
        query = self.search.get_text().lower()
        if self.view == "applications":
            self.fill_apps(query)
            return
        source = self.source.value
        shown = []
        for index, item in enumerate(self.items):
            group = "npm" if item["source"] in ("npm", "pnpm") else "other" if item["source"] in ("cargo", "bun", "local") else item["source"]
            if source not in ("all", group):
                continue
            if query and query not in f"{item['name']} {item.get('summary', '')}".lower():
                continue
            size = human_size(item["size"]) if item.get("size") else item.get("size_text", "")
            shown.append((index, item["name"], f"{item['source']}  {item['version'][:18]}  {size}", False))
        self.status.set_label(f"{len(shown)} of {len(self.items)}" if self.items else self.status.get_label())
        self.list.set_items(shown[:300])

    def select(self, index):
        item = self.items[index]
        while child := self.detail.get_first_child():
            self.detail.remove(child)
        self.detail.append(label(f"{item['name']}  {item['version']}", "accent"))
        if item.get("summary"):
            self.detail.append(label(item["summary"], "dim", wrap=True))
        actions = Gtk.Box(spacing=4, halign=Gtk.Align.END)
        actions.append(button("close", lambda: self.detail.set_visible(False)))
        actions.append(button("uninstall", lambda: self.uninstall(item), "danger"))
        self.detail.append(actions)
        self.detail.set_visible(True)

    def uninstall(self, item):
        command = UNINSTALL[item["source"]](item)
        confirm(self.panel, "uninstall", f"Remove {item['name']} ({item['source']})?\n\n{command}", "uninstall",
                lambda: (in_terminal(f"uninstall {item['name']}", command), self.detail.set_visible(False),
                         self.status.set_label("uninstalling in a terminal; search again when it's done")))

    # ----- applications -----

    def fill_apps(self, query):
        apps = sorted(Gio.AppInfo.get_all(), key=lambda a: (a.get_display_name() or "").lower())
        self.apps = {a.get_id(): a for a in apps if a.get_id()}
        shown = []
        for app_id, app in self.apps.items():
            if query and query not in f"{app.get_display_name()} {app_id} {app.get_commandline() or ''}".lower():
                continue
            local = os.path.exists(os.path.join(LOCAL_APPS, app_id))
            hidden = not app.should_show()
            detail = "  ".join(t for t in ("hidden" if hidden else "", "edited" if local else "") if t)
            shown.append((app_id, app.get_display_name() or app_id, detail, False))
        self.status.set_label(f"{len(shown)} applications · click one to edit its launcher entry")
        self.list.set_items([("", "+ new launcher entry", "", False)] + shown)

    def edit_app(self, app_id):
        app = Gio.DesktopAppInfo.new(app_id) if app_id else None
        values = {}
        if app:
            parser = configparser.RawConfigParser(interpolation=None, strict=False)
            parser.optionxform = str
            try:
                parser.read(app.get_filename())
                values = dict(parser["Desktop Entry"])
            except (configparser.Error, KeyError):
                values = {}
        form = Gtk.Box(orientation=V, css_classes=["page"])
        entries = {}
        for key, title in DESKTOP_FIELDS:
            entry = Gtk.Entry(text=values.get(key, ""), hexpand=True)
            entries[key] = entry
            form.append(row(title, entry))
        hidden = Toggle(lambda _on: None)
        hidden.set_active(values.get("NoDisplay", "false").lower() == "true")
        terminal = Toggle(lambda _on: None)
        terminal.set_active(values.get("Terminal", "false").lower() == "true")
        form.append(row("hide from the launcher", hidden))
        form.append(row("runs in a terminal", terminal))
        source = app.get_filename() if app else ""
        form.append(label(f"from {source}" if source else "a new entry in ~/.local/share/applications", "dim", "row", wrap=True))

        def save(response):
            if response == "delete":
                target = os.path.join(LOCAL_APPS, app_id)
                if os.path.exists(target):
                    os.remove(target)
                self.fill()
                return
            if response != "save":
                return
            name = entries["Name"].get_text().strip()
            if not name or not entries["Exec"].get_text().strip():
                self.status.set_label("a launcher entry needs a name and a command")
                return
            values.update({k: e.get_text().strip() for k, e in entries.items() if e.get_text().strip() or k in values})
            values["Type"] = values.get("Type", "Application")
            values["NoDisplay"] = "true" if hidden.active else "false"
            values["Terminal"] = "true" if terminal.active else "false"
            file_id = app_id or re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-") + ".desktop"
            os.makedirs(LOCAL_APPS, exist_ok=True)
            lines = ["[Desktop Entry]"] + [f"{k}={v}" for k, v in values.items() if v != ""]
            with open(os.path.join(LOCAL_APPS, file_id), "w") as f:
                f.write("\n".join(lines) + "\n")
            run("update-desktop-database", LOCAL_APPS)
            self.status.set_label(f"saved {file_id}")
            self.fill()

        buttons = [("cancel", None)]
        if app_id and os.path.exists(os.path.join(LOCAL_APPS, app_id)):
            buttons.append(("delete my version", "delete"))
        buttons.append(("save", "save"))
        dialog(self.panel, f"launcher · {values.get('Name', 'new')}", form, buttons, save, width=620)
