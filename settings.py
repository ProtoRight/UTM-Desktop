import json
from pathlib import Path

DEFAULTS: dict = {
    "last_port": "",
    "travel_limit_mm": 40.0,
    "load_limit_kg": 300.0,
    "load_drop_pct": 20.0,
    "load_drop_window": 10,
    "default_jog_speed": 50.0,
    "csv_export_dir": str(Path.home() / "Documents"),
    "load_cell_rating_kg": 500.0,
}

_path = Path(__file__).parent / "settings.json"
_data: dict = {}


def load() -> None:
    global _data
    if _path.exists():
        try:
            _data = json.loads(_path.read_text(encoding="utf-8"))
        except Exception:
            _data = {}
    for k, v in DEFAULTS.items():
        _data.setdefault(k, v)


def save() -> None:
    _path.write_text(json.dumps(_data, indent=2), encoding="utf-8")


def get(key: str):
    return _data.get(key, DEFAULTS.get(key))


def set(key: str, value) -> None:
    _data[key] = value
    save()
