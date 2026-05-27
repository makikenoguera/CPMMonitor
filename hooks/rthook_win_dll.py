"""
Runtime hook — Windows: agrega el directorio del exe al PATH de búsqueda de DLLs.
Necesario para que Qt5 encuentre sus DLLs cuando se lanza como subproceso (--panel, --mensajes).
"""
import os
import sys

if sys.platform == "win32":
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    # Agrega el directorio del exe al frente del PATH para que Windows encuentre Qt5*.dll
    os.environ["PATH"] = exe_dir + os.pathsep + os.environ.get("PATH", "")
    # Python 3.8+ usa os.add_dll_directory para la búsqueda de DLLs
    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(exe_dir)
        except Exception:
            pass
