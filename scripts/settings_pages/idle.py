import os

from .common import HOME, Choice, Page, Toggle, button, label, row, spawn

STAY_AWAKE = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.join(HOME, ".cache"), "stay-awake")
NEVER = [(0, "never")]
LOCK = NEVER + [(60, "1 minute"), (120, "2 minutes"), (300, "5 minutes"), (600, "10 minutes"), (900, "15 minutes"),
                (1800, "30 minutes"), (3600, "1 hour")]
SCREEN = NEVER + [(15, "15 seconds after locking"), (30, "30 seconds after locking"), (60, "1 minute after locking"),
                  (300, "5 minutes after locking")]
SUSPEND = NEVER + [(600, "10 minutes"), (1200, "20 minutes"), (1800, "30 minutes"), (3600, "1 hour"), (7200, "2 hours")]


class IdlePage(Page):
    name = "lock & sleep"

    def __init__(self, panel):
        super().__init__(panel)
        self.stay = Toggle(self.set_stay_awake)
        self.add(row("stay awake", self.stay, sub=label("never lock, blank or sleep until turned off", "dim")))

        self.section("when idle")
        self.lock = Choice(LOCK, lambda v: self.set_timers(lock=v))
        self.screen = Choice(SCREEN, lambda v: self.set_timers(screen=v))
        self.suspend = Choice(SUSPEND, lambda v: self.set_timers(suspend=v))
        self.add(row("lock the screen", self.lock), row("turn the display off", self.screen), row("sleep", self.suspend))

        self.section("now")
        self.add(row("lock", button("lock screen", lambda: spawn("swaylock", "-f"))),
                 row("sleep", button("sleep", lambda: spawn("systemctl", "suspend"))))

    def values(self):
        get = lambda key, default: int(self.sway(f"set $idle_{key}", default))
        lock, screen, suspend = get("lock", 300), get("screen_off", 330), get("suspend", 1800)
        return lock, screen, suspend

    def refresh(self):
        lock, screen, suspend = self.values()
        self.stay.set_active(os.path.exists(STAY_AWAKE))
        self.lock.set_value(lock)
        # the display timer is stored as seconds idle; show it relative to locking
        relative = screen - lock if lock and screen else screen
        self.screen.set_value(min((v for v, _t in SCREEN), key=lambda v: abs(v - relative)) if screen else 0)
        self.suspend.set_value(suspend)

    def set_timers(self, lock=None, screen=None, suspend=None):
        current_lock, current_screen, current_suspend = self.values()
        lock = current_lock if lock is None else lock
        relative = (current_screen - current_lock if current_lock and current_screen else current_screen)
        screen = relative if screen is None else screen
        suspend = current_suspend if suspend is None else suspend
        absolute = lock + screen if screen and lock else screen
        # reloading sway re-runs idle.sh with the new values
        self.stage(f"set $idle_lock {lock}", f"set $idle_screen_off {absolute}", f"set $idle_suspend {suspend}")

    def set_stay_awake(self, on):
        if on:
            open(STAY_AWAKE, "a").close()
        else:
            try:
                os.remove(STAY_AWAKE)
            except FileNotFoundError:
                pass
        lock, screen, suspend = self.values()
        spawn(os.path.join(HOME, ".local/bin/idle.sh"), str(lock), str(screen), str(suspend))
