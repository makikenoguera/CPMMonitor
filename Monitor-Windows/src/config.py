import json
import os


APPDATA_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'SumarteRed')
CONFIG_PATH = os.path.join(APPDATA_DIR, 'config.json')

DEFAULTS = {
    "venue_id": "",
    "api_key": "",
    "server_url": "https://monitor.sumartered.com",
    "min_detection_time": 30.0,
    "umbral_porcentaje": 80.0,
}


class ConfigManager:
    def __init__(self):
        self._data: dict = dict(DEFAULTS)
        os.makedirs(APPDATA_DIR, exist_ok=True)
        self.load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self) -> None:
        if not os.path.exists(CONFIG_PATH):
            self.save()
            return
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                stored = json.load(f)
            # Merge with defaults so new keys are always present
            merged = dict(DEFAULTS)
            merged.update(stored)
            self._data = merged
        except Exception:
            self._data = dict(DEFAULTS)

    def save(self) -> None:
        os.makedirs(APPDATA_DIR, exist_ok=True)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(self._data, f, indent=2)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def venue_id(self) -> str:
        return self._data.get('venue_id', '')

    @venue_id.setter
    def venue_id(self, value: str) -> None:
        self._data['venue_id'] = value

    @property
    def api_key(self) -> str:
        return self._data.get('api_key', '')

    @api_key.setter
    def api_key(self, value: str) -> None:
        self._data['api_key'] = value

    @property
    def server_url(self) -> str:
        return self._data.get('server_url', DEFAULTS['server_url'])

    @server_url.setter
    def server_url(self, value: str) -> None:
        self._data['server_url'] = value.rstrip('/')

    @property
    def min_detection_time(self) -> float:
        return float(self._data.get('min_detection_time', DEFAULTS['min_detection_time']))

    @min_detection_time.setter
    def min_detection_time(self, value: float) -> None:
        self._data['min_detection_time'] = float(value)

    @property
    def umbral_porcentaje(self) -> float:
        return float(self._data.get('umbral_porcentaje', DEFAULTS['umbral_porcentaje']))

    @umbral_porcentaje.setter
    def umbral_porcentaje(self, value: float) -> None:
        self._data['umbral_porcentaje'] = float(value)

    @property
    def is_activated(self) -> bool:
        """True when both venue_id and api_key are non-empty."""
        return bool(self._data.get('venue_id', '').strip()) and bool(self._data.get('api_key', '').strip())
