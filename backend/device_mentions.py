"""Recognize explicit names of the supported devices for command review."""

import re
from unicodedata import normalize


DEVICE_ALIASES = {
    "Light": ("light", "lights", "lamp", "lamps", "bulb", "bulbs", "tubelight", "tubelights",
              "tube light", "tube lights", "mi", "lok mae"),
    "Fan": ("fan", "fans", "pangka"),
    "AC": ("ac", "a c", "aircon", "air con", "air conditioner", "air conditioners", "air conditioning"),
    "Curtain": ("curtain", "curtains", "pardha"),
}
DEVICE_MENTIONS = {
    device: re.compile(r"\b(?:" + "|".join(map(re.escape, aliases)) + r")\b")
    for device, aliases in DEVICE_ALIASES.items()
}


def has_clear_device_mention(text, predicted_device):
    words = " ".join(re.findall(r"\w+", normalize("NFKC", text).casefold()))
    mentioned = {device for device, pattern in DEVICE_MENTIONS.items() if pattern.search(words)}
    return mentioned == {predicted_device}
