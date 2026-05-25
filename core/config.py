"""
CPM Tracks - Gestor de configuración
macOS: ~/Library/Application Support/CPMTracks/config.json
Windows: %APPDATA%/CPMTracks/config.json
"""
import json
import os
import platform

_IS_WIN = platform.system() == "Windows"

if _IS_WIN:
    DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "CPMTracks")
else:
    DATA_DIR = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "CPMTracks")

CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

DEFAULTS = {
    "id_local":        "SIN_CONFIGURAR",
    "nombre_local":    "",
    "tipo_local":      "",
    "api_endpoint":    "https://api.cpmtracks.com/v1/plays",
    "api_token":       "",
    "sync_intervalo":  30,
    "scan_intervalo":  3,
    "configurado":     False,
}


def cargar():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        guardar(DEFAULTS)
        return dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Merge con defaults para nuevas claves
        merged = dict(DEFAULTS)
        merged.update(data)
        return merged
    except Exception:
        return dict(DEFAULTS)


def guardar(config: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def esta_configurado():
    c = cargar()
    return c.get("configurado", False) and c.get("id_local", "SIN_CONFIGURAR") != "SIN_CONFIGURAR"
