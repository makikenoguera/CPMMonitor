"""SumarteRed Monitor - Windows Entry Point."""

import logging
import sys
import threading

# Configure logging early
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


def main() -> None:
    from src.config import ConfigManager
    from src.catalog_store import CatalogStore
    from src.catalog_manager import CatalogManager
    from src.local_matcher import LocalMatcher
    from src.database_manager import DatabaseManager
    from src.audio_capture import AudioCaptureManager
    from src.scanner_manager import ScannerManager
    from src.sync_manager import SyncManager
    from src.tray_ui import TrayUI

    logger.info("SumarteRed Monitor starting up")

    config = ConfigManager()
    db = DatabaseManager()
    catalog = CatalogStore()
    matcher = LocalMatcher()
    audio = AudioCaptureManager()
    scanner = ScannerManager(config, db, catalog, matcher, audio)
    sync = SyncManager(config, db)
    tray = TrayUI(config, scanner, sync)

    # Load catalog into matcher from local DB
    entries = catalog.load_all()
    matcher.reload(entries)
    logger.info("Loaded %d tracks from local catalog", len(entries))

    if config.is_activated:
        # Start background catalog sync
        threading.Thread(
            target=CatalogManager(config, catalog, matcher).check_for_updates,
            daemon=True,
            name='CatalogSync',
        ).start()

        # Start scanner and sync
        scanner.start()
        sync.start()
    else:
        logger.info("Not activated - waiting for configuration")

    # Run tray (blocks until user selects Salir)
    tray.run()

    logger.info("SumarteRed Monitor exiting")
    sys.exit(0)


if __name__ == '__main__':
    main()
