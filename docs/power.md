# Idle, lid, locking, and sleep

[`idle.sh`](../scripts/idle.sh) starts swayidle with the timers set at the top of the Sway config:

- lock after 5 minutes idle
- turn the screen off 30 seconds later
- suspend after 30 minutes

It also locks before sleeping. It runs on every Sway reload, so new timers from Settings take effect right away.

## The lid

Closing the lid goes through [`lid.sh`](../scripts/lid.sh) instead of logind:

- **On its own:** the laptop sleeps (or locks, or just turns the screen off, set in Settings → lock & sleep).
- **With an external display:** only the laptop screen turns off, so you can keep working.
- **Opening the lid** turns the screen back on.

## Stay awake

**Stay awake** keeps the laptop from locking, blanking, or sleeping, and closing the lid only turns the screen off. Turn it on from Spotlight or Settings → lock & sleep. While it's on, a coffee cup shows in the bar; click it to turn stay awake off.

Everything goes through [`stay-awake.sh`](../scripts/stay-awake.sh) `on`, `off`, or `toggle`, which creates or removes `~/.cache/stay-awake` and restarts swayidle with the same timers.
