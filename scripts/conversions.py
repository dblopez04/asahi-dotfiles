"""Unit, currency and time zone conversions for Spotlight.

    5 km in miles · 72f to c · 3 cups in ml · 60 mph to kph · 2.5 gb in mib
    20 usd to eur · 100 yen in dollars       (daily rates from frankfurter.dev, cached)
    time in tokyo · 3pm in london · 9:30am chicago to berlin

convert(query) returns [(answer, detail)] or None. Currency needs rates: when they aren't cached yet,
convert() returns None and currency_request(query) says which base to fetch (fetch_rates, on a thread).
"""
import json
import os
import re
import time
import urllib.request
import zoneinfo
from datetime import datetime

CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "spotlight")
RATES_URL = "https://api.frankfurter.dev/v1/latest?base={}"
RATES_MAX_AGE = 12 * 3600

# unit: (category, factor to the category's base unit)
UNITS = {}


def _units(category, factor, *names):
    for name in names:
        UNITS[name] = (category, factor)


_units("length", 0.001, "mm", "millimeter", "millimeters")
_units("length", 0.01, "cm", "centimeter", "centimeters")
_units("length", 1, "m", "meter", "meters", "metre", "metres")
_units("length", 1000, "km", "kilometer", "kilometers", "kilometre", "kilometres")
_units("length", 0.0254, "in", "inch", "inches")
_units("length", 0.3048, "ft", "foot", "feet")
_units("length", 0.9144, "yd", "yard", "yards")
_units("length", 1609.344, "mi", "mile", "miles")
_units("mass", 0.001, "g", "gram", "grams")
_units("mass", 0.000001, "mg", "milligram", "milligrams")
_units("mass", 1, "kg", "kilo", "kilos", "kilogram", "kilograms")
_units("mass", 0.028349523, "oz", "ounce", "ounces")
_units("mass", 0.45359237, "lb", "lbs", "pound", "pounds")
_units("mass", 6.35029318, "st", "stone")
_units("volume", 0.001, "ml", "milliliter", "milliliters")
_units("volume", 1, "l", "liter", "liters", "litre", "litres")
_units("volume", 0.2365882, "cup", "cups")
_units("volume", 0.0295735, "floz", "fl oz")
_units("volume", 0.0147868, "tbsp", "tablespoon", "tablespoons")
_units("volume", 0.00492892, "tsp", "teaspoon", "teaspoons")
_units("volume", 0.473176, "pint", "pints")
_units("volume", 3.78541, "gal", "gallon", "gallons")
_units("speed", 1, "m/s", "mps")
_units("speed", 0.277778, "kph", "kmh", "km/h")
_units("speed", 0.44704, "mph")
_units("speed", 0.514444, "knot", "knots", "kn")
_units("data", 1, "b", "byte", "bytes")
_units("data", 1e3, "kb", "kilobyte", "kilobytes")
_units("data", 1e6, "mb", "megabyte", "megabytes")
_units("data", 1e9, "gb", "gigabyte", "gigabytes")
_units("data", 1e12, "tb", "terabyte", "terabytes")
_units("data", 1024, "kib")
_units("data", 1024 ** 2, "mib")
_units("data", 1024 ** 3, "gib")
_units("data", 1024 ** 4, "tib")
_units("time", 1, "sec", "secs", "second", "seconds")
_units("time", 60, "min", "mins", "minute", "minutes")
_units("time", 3600, "h", "hr", "hrs", "hour", "hours")
_units("time", 86400, "day", "days")
_units("time", 604800, "week", "weeks")
_units("time", 31557600, "year", "years")
TEMPERATURE = {"c": "c", "°c": "c", "celsius": "c", "f": "f", "°f": "f", "fahrenheit": "f", "k": "k", "kelvin": "k"}

CURRENCY_NAMES = {"dollar": "USD", "dollars": "USD", "bucks": "USD", "$": "USD", "euro": "EUR", "euros": "EUR",
                  "€": "EUR", "yen": "JPY", "¥": "JPY", "pound sterling": "GBP", "quid": "GBP", "£": "GBP",
                  "peso": "MXN", "pesos": "MXN", "rupee": "INR", "rupees": "INR", "won": "KRW", "yuan": "CNY",
                  "franc": "CHF", "francs": "CHF", "cad": "CAD", "aud": "AUD"}
CURRENCIES = {"USD", "EUR", "JPY", "GBP", "AUD", "CAD", "CHF", "CNY", "HKD", "NZD", "SEK", "KRW", "SGD", "NOK", "MXN",
              "INR", "BRL", "ZAR", "DKK", "PLN", "TRY", "THB", "IDR", "HUF", "CZK", "ILS", "PHP", "MYR", "RON",
              "BGN", "ISK"}

PLACES = {"nyc": "America/New_York", "new york": "America/New_York", "boston": "America/New_York",
          "miami": "America/New_York", "est": "America/New_York", "edt": "America/New_York", "eastern": "America/New_York",
          "la": "America/Los_Angeles", "los angeles": "America/Los_Angeles", "sf": "America/Los_Angeles",
          "san francisco": "America/Los_Angeles", "seattle": "America/Los_Angeles", "pst": "America/Los_Angeles",
          "pdt": "America/Los_Angeles", "pacific": "America/Los_Angeles", "dallas": "America/Chicago",
          "austin": "America/Chicago", "houston": "America/Chicago", "texas": "America/Chicago", "cst": "America/Chicago",
          "cdt": "America/Chicago", "central": "America/Chicago", "mst": "America/Denver", "mountain": "America/Denver",
          "hawaii": "Pacific/Honolulu", "uk": "Europe/London", "england": "Europe/London", "france": "Europe/Paris",
          "germany": "Europe/Berlin", "spain": "Europe/Madrid", "italy": "Europe/Rome", "japan": "Asia/Tokyo",
          "korea": "Asia/Seoul", "china": "Asia/Shanghai", "beijing": "Asia/Shanghai", "india": "Asia/Kolkata",
          "delhi": "Asia/Kolkata", "mumbai": "Asia/Kolkata", "bangalore": "Asia/Kolkata", "australia": "Australia/Sydney",
          "brazil": "America/Sao_Paulo", "mexico": "America/Mexico_City", "utc": "UTC", "gmt": "UTC", "here": "local",
          "local": "local"}


def number(text):
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def fmt(value):
    if value == 0:
        return "0"
    if abs(value) >= 1e15 or abs(value) < 1e-6:
        return f"{value:.4g}"
    rounded = round(value, 4 if abs(value) < 10 else 2)
    return f"{rounded:,.4f}".rstrip("0").rstrip(".") if abs(value) < 10 else f"{rounded:,.2f}".rstrip("0").rstrip(".")


###############
### PARSING ###
###############

PATTERN = re.compile(r"^\s*(-?[\d,]*\.?\d+)\s*(.+?)\s+(?:in|to|as|into)\s+(.+?)\s*$", re.I)


def convert(query):
    return units(query) or temperature(query) or currency(query) or timezone(query)


def units(query):
    match = PATTERN.match(query.lower())
    if not match:
        return None
    amount, source, target = number(match.group(1)), match.group(2).strip(), match.group(3).strip()
    if amount is None or source not in UNITS or target not in UNITS:
        return None
    (category, from_factor), (other, to_factor) = UNITS[source], UNITS[target]
    if category != other:
        return None
    value = amount * from_factor / to_factor
    return [(f"{fmt(value)} {target}", f"{fmt(amount)} {source} · enter copies")]


def temperature(query):
    match = PATTERN.match(query.lower()) or re.match(r"^\s*(-?[\d.]+)\s*(°?[cfk]|celsius|fahrenheit|kelvin)\s+(?:in|to)\s+(°?[cfk]|celsius|fahrenheit|kelvin)\s*$", query.lower())
    if not match:
        return None
    amount, source, target = number(match.group(1)), TEMPERATURE.get(match.group(2).strip()), TEMPERATURE.get(match.group(3).strip())
    if amount is None or not source or not target or source == target:
        return None
    celsius = {"c": amount, "f": (amount - 32) * 5 / 9, "k": amount - 273.15}[source]
    value = {"c": celsius, "f": celsius * 9 / 5 + 32, "k": celsius + 273.15}[target]
    symbol = {"c": "°C", "f": "°F", "k": "K"}
    return [(f"{fmt(value)}{symbol[target]}", f"{fmt(amount)}{symbol[source]} · enter copies")]


def currency_codes(query):
    match = PATTERN.match(query) or re.match(r"^\s*([$€£¥])\s*([\d,]*\.?\d+)\s+(?:in|to)\s+(.+?)\s*$", query)
    if not match:
        return None
    if match.group(1) in "$€£¥":
        amount, source, target = number(match.group(2)), match.group(1), match.group(3)
    else:
        amount, source, target = number(match.group(1)), match.group(2), match.group(3)
    code = lambda name: CURRENCY_NAMES.get(name.lower()) or (name.upper() if name.upper() in CURRENCIES else None)
    source, target = code(source.strip()), code(target.strip())
    if amount is None or not source or not target or source == target:
        return None
    return amount, source, target


def cached_rates(base):
    try:
        with open(os.path.join(CACHE, f"rates-{base}.json")) as f:
            data = json.load(f)
        if time.time() - data.get("fetched", 0) < RATES_MAX_AGE:
            return data
    except (OSError, ValueError):
        pass
    return None


def fetch_rates(base):
    """Download today's rates for base (blocking; call on a thread). Returns True on success."""
    try:
        request = urllib.request.Request(RATES_URL.format(base), headers={"User-Agent": "dotfiles-spotlight"})
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.load(response)
        data["fetched"] = time.time()
        os.makedirs(CACHE, exist_ok=True)
        with open(os.path.join(CACHE, f"rates-{base}.json"), "w") as f:
            json.dump(data, f)
        return True
    except (OSError, ValueError):
        return False


def currency_request(query):
    """The base currency whose rates query needs, if they aren't cached; else None."""
    codes = currency_codes(query)
    return codes[1] if codes and not cached_rates(codes[1]) else None


def currency(query):
    codes = currency_codes(query)
    if not codes:
        return None
    amount, source, target = codes
    data = cached_rates(source)
    if not data or target not in data.get("rates", {}):
        return None
    value = amount * data["rates"][target]
    return [(f"{value:,.2f} {target}", f"{fmt(amount)} {source} · rates from {data.get('date', 'today')} · enter copies")]


def zone(name):
    name = name.strip().lower().removesuffix(" time").strip()
    if name in PLACES:
        return None if PLACES[name] == "local" else zoneinfo.ZoneInfo(PLACES[name])
    key = name.replace(" ", "_")
    for candidate in sorted(zoneinfo.available_timezones()):
        if candidate.lower().rsplit("/", 1)[-1] == key:
            return zoneinfo.ZoneInfo(candidate)
    raise KeyError(name)


def clock(text):
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text.strip().lower())
    if not match or (not match.group(2) and not match.group(3)):
        return None
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    if match.group(3) == "pm" and hour < 12:
        hour += 12
    elif match.group(3) == "am" and hour == 12:
        hour = 0
    return (hour, minute) if hour < 24 and minute < 60 else None


def label(moment, place):
    return moment.strftime("%-I:%M %p").lower() + f" in {place}" + moment.strftime(" · %a %b %-d").lower()


def timezone(query):
    q = query.strip().lower()
    try:
        match = re.fullmatch(r"(?:what time is it in|time in|current time in)\s+(.+)|(.+?)\s+time", q)
        if match:
            place = (match.group(1) or match.group(2)).strip()
            now = datetime.now(zone(place))
            return [(label(now, place), "current time · enter copies")]
        match = re.fullmatch(r"(.+?)(?:\s+(.+?))?\s+(?:in|to)\s+(.+)", q)
        if match and clock(match.group(1)):
            hour, minute = clock(match.group(1))
            source = zone(match.group(2)) if match.group(2) else None
            target_place = match.group(3).strip()
            start = datetime.now(source).replace(hour=hour, minute=minute, second=0, microsecond=0)
            moment = start.astimezone(zone(target_place))
            origin = f"{match.group(1)} {match.group(2) or 'here'}"
            return [(label(moment, target_place), f"{origin} · enter copies")]
    except (KeyError, zoneinfo.ZoneInfoNotFoundError, ValueError):
        return None
    return None
