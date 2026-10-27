"""Which edition of Kaizen this is.

The public edition has no edition.json. Licensed editions (built with `installer\\build.py --edition <id>`) ship an
app\\edition.json copied from editions\\<id>.json that names the organisation and switches features off.
"""
import json
import os

PUBLIC = {
    "id": "public",
    "name": "",
    "org": "",
    "grant": "",
    "allow_uninstall": True,
    "uninstall_note": "",
}

_cache = None


def get():
    global _cache
    if _cache is None:
        data = dict(PUBLIC)
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "edition.json")
        try:
            with open(path, encoding="utf-8") as f:
                data.update(json.load(f))
        except (OSError, ValueError):
            pass
        _cache = data
    return _cache
