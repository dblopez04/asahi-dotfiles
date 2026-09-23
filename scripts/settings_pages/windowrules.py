import json
import re

from gi.repository import Gio, Gtk

import dotconfig

from .common import V, Choice, ItemList, Page, Toggle, button, label, row, run

SIZES = [("", "leave it"), ("600 400", "small · 600×400"), ("900 600", "medium · 900×600"),
         ("1200 800", "large · 1200×800"), ("80 ppt 80 ppt", "80% of the screen"), ("480 270", "video · 480×270")]
POSITIONS = [("", "leave it"), ("center", "centered"), ("corner", "bottom right corner"), ("cursor", "at the mouse")]
WORKSPACES = [("", "current workspace")] + [(str(n), f"workspace {n}") for n in range(1, 11)]
OPACITY = [("", "opaque"), ("0.95", "95%"), ("0.9", "90%"), ("0.85", "85%"), ("0.8", "80%")]
RULE = re.compile(r"^\s*for_window\s+(\[.*?\])\s+(.+?)\s*$")
KNOWN = {"dev.dotfiles.SettingsPanel": "Settings", "dev.dotfiles.WallpaperPicker": "Wallpaper Picker",
         "dev.dotfiles.QuickLook": "Quick Look", "dev.dotfiles.Cheatsheet": "Shortcut Cheat Sheet",
         "dev.dotfiles.Spotlight": "Spotlight", "dev.dotfiles.walwrite": "Walwrite", "walwrite": "Walwrite",
         "org.mozilla.firefox": "Firefox", "firefox": "Firefox", "feh": "feh (images)",
         "SettingsPanel": "Settings", "WallpaperPicker": "Wallpaper Picker"}


def criteria_of(text):
    return dict(re.findall(r'(\w+)="((?:[^"\\]|\\.)*)"', text))


def app_name(criteria):
    """A readable name for a rule's window: the desktop entry's name when there is one."""
    ident = criteria.get("app_id") or criteria.get("class") or ""
    # rules are regexes: "^(dev\.dotfiles\.)?walwrite$" or "^(firefox|org\.mozilla\.firefox)$" -> a plain id
    plain = re.sub(r"\(([^()|]*)\)\?", "", ident.strip("^$")).replace("\\.", ".")
    plain = plain.strip("()").split("|")[0]
    names = [KNOWN[p] for p in plain.strip("()").split("|") if p in KNOWN]
    if "(" in ident and "|" in ident.split("(", 1)[1]:  # an alternation of several apps
        alternatives = re.search(r"\((.*)\)", ident).group(1).replace("\\.", ".").split("|")
        names = [KNOWN.get(a, a) for a in alternatives]
        if len(set(names)) == 1:
            names = names[:1]
        if len(names) > 1:
            return " / ".join(names) + (f" · “{criteria['title'].strip('^$')}”" if criteria.get("title") else "")
        plain = alternatives[0]
    if plain in KNOWN:
        name = KNOWN[plain]
        if criteria.get("title"):
            name += f" · “{criteria['title'].strip('^$')}”"
        return name
    for candidate in (f"{plain}.desktop", f"{plain.lower()}.desktop"):
        try:
            info = Gio.DesktopAppInfo.new(candidate)
        except TypeError:
            info = None
        if info:
            name = info.get_display_name()
            break
    else:
        name = plain or "any window"
    if criteria.get("title"):
        name += f" · “{criteria['title'].strip('^$')}”"
    return name


def rules():
    """{criteria text: command} from the saved config with staged changes on top (nop = removed)."""
    found = {}
    for line in dotconfig.read(dotconfig.SWAY_CONFIG).splitlines():
        if match := RULE.match(line):
            found[match.group(1)] = match.group(2)
    for key, line in dotconfig.sway_pending().items():
        if key.startswith("for_window") and (match := RULE.match(line)):
            if match.group(2) == "nop":
                found.pop(match.group(1), None)
            else:
                found[match.group(1)] = match.group(2)
    return found


def parse_command(command):
    """The parts of a rule this page understands, plus everything else kept as-is."""
    parts = [p.strip() for p in command.split(",") if p.strip()]
    rule = {"float": False, "sticky": False, "border": False, "size": "", "position": "", "workspace": "",
            "opacity": "", "extra": []}
    for part in parts:
        if part == "floating enable":
            rule["float"] = True
        elif part == "sticky enable":
            rule["sticky"] = True
        elif part == "border none":
            rule["border"] = True
        elif m := re.fullmatch(r"resize set (.+)", part):
            rule["size"] = m.group(1)
        elif part == "move position center":
            rule["position"] = "center"
        elif part == "move position cursor":
            rule["position"] = "cursor"
        elif part.startswith("move position 100 ppt 100 ppt"):
            rule["position"] = "corner"
        elif rule["position"] == "corner" and re.fullmatch(r"move (left|up) \d+ px", part):
            pass  # the corner offsets that go with it
        elif m := re.fullmatch(r"move (?:container )?to workspace (?:number )?(\d+)", part):
            rule["workspace"] = m.group(1)
        elif m := re.fullmatch(r"opacity ([\d.]+)", part):
            rule["opacity"] = m.group(1)
        else:
            rule["extra"].append(part)
    return rule


def summary(command):
    rule = parse_command(command)
    bits = (["floats"] if rule["float"] else []) + (["on every workspace"] if rule["sticky"] else [])
    if rule["size"]:
        bits.append(dict(SIZES).get(rule["size"], rule["size"]).split(" · ")[-1])
    if rule["position"]:
        bits.append(dict(POSITIONS)[rule["position"]])
    if rule["workspace"]:
        bits.append(f"workspace {rule['workspace']}")
    if rule["opacity"]:
        bits.append(f"{float(rule['opacity']) * 100:.0f}% opacity")
    if rule["border"]:
        bits.append("no border")
    bits += rule["extra"]
    return ", ".join(bits) or "no changes"


class WindowRulesPage(Page):
    """How specific apps' windows open: floating, size, position, workspace, opacity."""
    name = "window rules"

    def __init__(self, panel):
        super().__init__(panel)
        self.editing = None  # criteria text of the rule being edited, or "" for a new one
        self.section("rules", button("add rule", lambda: self.edit("")))
        self.list = ItemList(self.edit, empty="no window rules")
        self.add(self.list)
        self.add(label("rules apply to windows opened after the change", "dim", "row"))

        self.editor = Gtk.Box(orientation=V, visible=False)
        self.section_box = None
        self.app = Choice([], lambda _v: None)
        self.app_entry = Gtk.Entry(placeholder_text="or type an app id", width_chars=22)
        self.title_entry = Gtk.Entry(placeholder_text="window title contains (optional)", hexpand=True)
        self.float = Toggle(lambda _on: None)
        self.sticky = Toggle(lambda _on: None)
        self.border = Toggle(lambda _on: None)
        self.size = Choice(SIZES, lambda _v: None)
        self.position = Choice(POSITIONS, lambda _v: None)
        self.workspace = Choice(WORKSPACES, lambda _v: None)
        self.opacity = Choice(OPACITY, lambda _v: None)
        self.status = label("", "dim", "row")
        actions = Gtk.Box(spacing=4, halign=Gtk.Align.END, css_classes=["row"])
        self.remove_button = button("remove rule", self.remove, "danger")
        for widget in (self.remove_button, button("cancel", self.close_editor), button("save rule", self.save)):
            actions.append(widget)
        for widget in (row("app", self.app, self.app_entry), row("title", self.title_entry),
                       row("float", self.float), row("on every workspace", self.sticky, sub=label("sticky", "dim")),
                       row("size", self.size), row("position", self.position), row("open on", self.workspace),
                       row("opacity", self.opacity), row("hide the border", self.border), self.status, actions):
            self.editor.append(widget)
        self.editor_header = label("", "section", "section-row")
        self.editor.prepend(self.editor_header)
        self.add(self.editor)

    def refresh(self):
        self.rules = rules()
        items = sorted(((key, app_name(criteria_of(key)), summary(command), False) for key, command in self.rules.items()),
                       key=lambda i: i[1].lower())
        self.list.set_items(items)

    @staticmethod
    def open_apps():
        try:
            tree = json.loads(run("swaymsg", "-r", "-t", "get_tree", timeout=3) or "{}")
        except ValueError:
            return []
        found = {}

        def walk(node):
            ident = node.get("app_id") or (node.get("window_properties") or {}).get("class")
            if ident and node.get("pid"):
                found[ident] = app_name({"app_id": ident})
            for child in node.get("nodes", []) + node.get("floating_nodes", []):
                walk(child)

        walk(tree)
        return sorted(found.items(), key=lambda kv: kv[1].lower())

    def edit(self, key):
        self.editing = key
        criteria = criteria_of(key) if key else {}
        rule = parse_command(self.rules.get(key, "")) if key else parse_command("floating enable")
        ident = (criteria.get("app_id") or criteria.get("class") or "").strip("^$").replace("\\.", ".")
        options = self.open_apps()
        if ident and ident not in dict(options):
            options.append((ident, app_name({"app_id": ident})))
        self.app.set_options([("", "pick an open app")] + options)
        self.app.set_value(ident if ident in dict(options) else "")
        self.app_entry.set_text("" if ident in dict(options) else ident)
        self.title_entry.set_text(criteria.get("title", "").strip("^$"))
        self.float.set_active(rule["float"])
        self.sticky.set_active(rule["sticky"])
        self.border.set_active(rule["border"])
        self.size.set_value(rule["size"] if rule["size"] in dict(SIZES) else "")
        self.position.set_value(rule["position"])
        self.workspace.set_value(rule["workspace"])
        self.opacity.set_value(rule["opacity"] if rule["opacity"] in dict(OPACITY) else "")
        self.extra = rule["extra"]
        self.editor_header.set_label(("edit rule: " + app_name(criteria)) if key else "new rule:")
        self.remove_button.set_visible(bool(key))
        self.status.set_label("keeps: " + ", ".join(self.extra) if self.extra else "")
        self.editor.set_visible(True)

    def build(self):
        ident = self.app_entry.get_text().strip() or self.app.value or ""
        if not ident:
            return None, "pick an app or type its app id"
        # sway matches app_id for wayland apps and class for xwayland ones
        attribute = "app_id" if not ident[:1].isupper() or "." in ident else "app_id"
        criteria = f'{attribute}="^{re.escape(ident)}$"'
        title = self.title_entry.get_text().strip()
        if title:
            criteria += f' title="{re.escape(title)}"'
        parts = []
        if self.float.active:
            parts.append("floating enable")
        if self.sticky.active:
            parts.append("sticky enable")
        if self.size.value:
            parts.append(f"resize set {self.size.value}")
        if self.position.value == "center":
            parts.append("move position center")
        elif self.position.value == "cursor":
            parts.append("move position cursor")
        elif self.position.value == "corner":
            width, height = (self.size.value or "480 270").split()[:2] if "ppt" not in (self.size.value or "") else ("480", "270")
            parts += ["move position 100 ppt 100 ppt", f"move left {int(width) + 16} px", f"move up {int(height) + 16} px"]
        if self.workspace.value:
            parts.append(f"move container to workspace number {self.workspace.value}")
        if self.opacity.value:
            parts.append(f"opacity {self.opacity.value}")
        if self.border.active:
            parts.append("border none")
        parts += self.extra
        if not parts:
            return None, "turn something on for this rule, or remove it"
        return f"for_window [{criteria}] {', '.join(parts)}", None

    def save(self):
        line, problem = self.build()
        if problem:
            self.status.set_label(problem)
            return
        new_key = RULE.match(line).group(1)
        lines = [line]
        if self.editing and self.editing != new_key:
            lines.insert(0, f"for_window {self.editing} nop")  # the app or title changed: drop the old rule
        self.stage(*lines)
        self.close_editor()
        self.refresh()

    def remove(self):
        if self.editing:
            self.stage(f"for_window {self.editing} nop")
        self.close_editor()
        self.refresh()

    def close_editor(self):
        self.editing = None
        self.editor.set_visible(False)

    def escape(self, focus):
        if self.editor.get_visible():
            self.close_editor()
            return True
        return False
