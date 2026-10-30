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
    tray = TrayUI(config, scanner, sync, db)

    # Load catalog into matcher from local DB
    entries = catalog.load_all()
    matcher.reload(entries)
    logger.info("Loaded %d tracks from local catalog", len(entries))

    if config.is_activated:
        catalog_mgr = CatalogManager(config, catalog, matcher)

        def _catalog_loop() -> None:
            """Sync catalog at startup then every 6 hours. Retries every 60s if empty."""
            import time
            while True:
                catalog_mgr.check_for_updates()
                # If catalog is still empty after sync, retry sooner
                if catalog.track_count == 0:
                    logger.warning("Catalog still empty after sync, retrying in 60s")
                    time.sleep(60)
                else:
                    time.sleep(6 * 3600)

        threading.Thread(target=_catalog_loop, daemon=True, name='CatalogSync').start()

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
