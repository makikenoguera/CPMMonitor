import logging
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

import pystray
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

APP_NAME = "SumarteRed Monitor"


# ------------------------------------------------------------------
# Icon generation
# ------------------------------------------------------------------

def make_icon(active: bool) -> Image.Image:
    """Generate a 64x64 tray icon programmatically."""
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (255, 107, 53, 255) if active else (128, 128, 128, 255)
    draw.ellipse([4, 4, 60, 60], fill=color)
    return img


# ------------------------------------------------------------------
# Config dialog
# ------------------------------------------------------------------

class ConfigDialog:
    def __init__(self, config, api_client_factory) -> None:
        self._config = config
        self._api_client_factory = api_client_factory
        self._root: Optional[tk.Tk] = None

    def show(self) -> None:
        """Show (or bring to front) the config dialog in the main thread."""
        # Must run in a thread to avoid blocking pystray
        t = threading.Thread(target=self._run_dialog, daemon=True, name='ConfigDialog')
        t.start()

    def _run_dialog(self) -> None:
        root = tk.Tk()
        self._root = root
        root.title(f"{APP_NAME} - Configuración")
        root.resizable(False, False)
        root.attributes('-topmost', True)

        pad = {'padx': 10, 'pady': 6}

        # --- Venue ID ---
        tk.Label(root, text="Venue ID:", anchor='w').grid(row=0, column=0, sticky='w', **pad)
        venue_var = tk.StringVar(value=self._config.venue_id)
        venue_entry = tk.Entry(root, textvariable=venue_var, width=36)
        venue_entry.grid(row=0, column=1, **pad)

        # --- API Key ---
        tk.Label(root, text="API Key:", anchor='w').grid(row=1, column=0, sticky='w', **pad)
        api_key_var = tk.StringVar(value=self._config.api_key)
        api_key_entry = tk.Entry(root, textvariable=api_key_var, width=36, show='*')
        api_key_entry.grid(row=1, column=1, **pad)

        # --- Show/Hide API Key ---
        def toggle_show():
            api_key_entry.config(show='' if show_var.get() else '*')

        show_var = tk.BooleanVar(value=False)
        tk.Checkbutton(root, text="Mostrar API Key", variable=show_var, command=toggle_show).grid(
            row=2, column=1, sticky='w', padx=10
        )

        # --- Server URL ---
        tk.Label(root, text="Servidor URL:", anchor='w').grid(row=3, column=0, sticky='w', **pad)
        server_var = tk.StringVar(value=self._config.server_url)
        tk.Entry(root, textvariable=server_var, width=36).grid(row=3, column=1, **pad)

        # --- Status label ---
        status_var = tk.StringVar(value="")
        status_label = tk.Label(root, textvariable=status_var, fg='gray', wraplength=300, justify='left')
        status_label.grid(row=4, column=0, columnspan=2, **pad)

        # --- Buttons ---
        btn_frame = tk.Frame(root)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=(0, 10))

        def verify_and_save():
            vid = venue_var.get().strip()
            akey = api_key_var.get().strip()
            surl = server_var.get().strip().rstrip('/')

            if not vid or not akey or not surl:
                status_var.set("Por favor completa todos los campos.")
                status_label.config(fg='red')
                return

            status_var.set("Verificando...")
            status_label.config(fg='gray')
            root.update_idletasks()

            from src.api_client import APIClient
            # Temporary config-like object for verification
            class TempConfig:
                api_key = akey
                server_url = surl

            client = APIClient(TempConfig())
            result = client.verify_venue(vid, akey, surl)

            if result and result.get('ok'):
                nombre = result.get('nombre_local', vid)
                status_var.set(f"Verificado: {nombre}")
                status_label.config(fg='green')

                # Save to config
                self._config.venue_id = vid
                self._config.api_key = akey
                self._config.server_url = surl
                self._config.save()

                root.after(1500, root.destroy)
            else:
                status_var.set("Error: no se pudo verificar el local. Revisa los datos.")
                status_label.config(fg='red')

        def cancel():
            root.destroy()

        tk.Button(btn_frame, text="Verificar y Guardar", command=verify_and_save, width=20).pack(
            side='left', padx=5
        )
        tk.Button(btn_frame, text="Cancelar", command=cancel, width=10).pack(side='left', padx=5)

        root.mainloop()
        self._root = None


# ------------------------------------------------------------------
# Tray UI
# ------------------------------------------------------------------

class TrayUI:
    def __init__(self, config, scanner, sync_manager) -> None:
        self._config = config
        self._scanner = scanner
        self._sync = sync_manager
        self._icon: Optional[pystray.Icon] = None
        self._active = False
        self._status_text = ""
        self._config_dialog = ConfigDialog(config, None)

        # Wire scanner status callback
        scanner.on_status_change = self._on_scanner_status

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Build the tray icon and block until exit."""
        self._active = self._scanner.is_scanning
        self._update_status_text()
        icon_image = make_icon(self._active)

        self._icon = pystray.Icon(
            name=APP_NAME,
            icon=icon_image,
            title=self._tooltip(),
            menu=self._build_menu(),
        )
        self._icon.run()

    # ------------------------------------------------------------------
    # Menu actions
    # ------------------------------------------------------------------

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(
                lambda item: "⏹ Detener" if self._scanner.is_scanning else "▶ Iniciar",
                self._toggle_scanning,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Configuración...", self._open_config),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", self._quit),
        )

    def _toggle_scanning(self, icon, item) -> None:
        if self._scanner.is_scanning:
            self._scanner.stop()
            self._active = False
            self._status_text = "Detenido"
        else:
            if not self._config.is_activated:
                self._status_text = "Sin configurar"
                self._active = False
            else:
                self._scanner.start()
                self._active = True
                self._status_text = "Escuchando..."
        self._refresh_icon()

    def _open_config(self, icon, item) -> None:
        self._config_dialog.show()

    def _quit(self, icon, item) -> None:
        logger.info("TrayUI: quitting")
        try:
            self._scanner.stop()
        except Exception:
            pass
        try:
            self._sync.stop()
        except Exception:
            pass
        icon.stop()

    # ------------------------------------------------------------------
    # Status updates
    # ------------------------------------------------------------------

    def _on_scanner_status(self, status: str) -> None:
        self._status_text = status
        self._active = (status == "Escuchando...")
        if self._icon is not None:
            self._refresh_icon()

    def _update_status_text(self) -> None:
        if not self._config.is_activated:
            self._status_text = "Sin configurar"
            self._active = False
        elif self._scanner.is_scanning:
            self._status_text = "Escuchando..."
            self._active = True
        else:
            self._status_text = "Detenido"
            self._active = False

    def _tooltip(self) -> str:
        return f"{APP_NAME} - {self._status_text}"

    def _refresh_icon(self) -> None:
        if self._icon is None:
            return
        self._icon.icon = make_icon(self._active)
        self._icon.title = self._tooltip()
