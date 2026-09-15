from .common import Page, Toggle, button, label, row, run, spawn


class NotificationsPage(Page):
    name = "notifications"
    interval = 3

    def __init__(self, panel):
        super().__init__(panel)
        self.dnd = Toggle(lambda on: run("swaync-client", "-dn" if on else "-df"))
        self.count = label("", "dim")
        self.add(
            row("do not disturb", self.dnd),
            row("notifications", button("clear all", self.clear), sub=self.count),
            row("notification center", button("open", lambda: spawn("swaync-client", "-op"))),
        )

    def refresh(self):
        self.dnd.set_active(run("swaync-client", "-D", timeout=3).strip() == "true")
        count = run("swaync-client", "-c", timeout=3).strip() or "0"
        self.count.set_label("none" if count == "0" else f"{count} unread")

    def clear(self):
        run("swaync-client", "-C")
        self.refresh()
