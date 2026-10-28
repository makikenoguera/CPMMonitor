import logging
import threading
from typing import TYPE_CHECKING

import requests

from src.catalog_store import CatalogStore

if TYPE_CHECKING:
    from src.config import ConfigManager
    from src.local_matcher import LocalMatcher

logger = logging.getLogger(__name__)


class CatalogManager:
    def __init__(self, config: 'ConfigManager', store: CatalogStore, matcher: 'LocalMatcher'):
        self._config = config
        self._store = store
        self._matcher = matcher
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_for_updates(self) -> None:
        """Synchronous method - run in a background thread."""
        if not self._config.is_activated:
            logger.info("CatalogManager: not activated, skipping sync")
            return

        with self._lock:
            try:
                self._sync()
            except Exception as exc:
                logger.error("CatalogManager.check_for_updates error: %s", exc, exc_info=True)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _headers(self) -> dict:
        return {'X-API-Key': self._config.api_key}

    def _base_url(self) -> str:
        return self._config.server_url.rstrip('/')

    def _get_server_version(self) -> int | None:
        url = f"{self._base_url()}/v1/catalog/version"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return int(data.get('version', 0))
        except Exception as exc:
            logger.error("CatalogManager: error fetching server version: %s", exc)
            return None

    def _fetch_full(self) -> dict | None:
        url = f"{self._base_url()}/v1/catalog/full"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=60)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error("CatalogManager: error fetching full catalog: %s", exc)
            return None

    def _fetch_delta(self, since: int) -> dict | None:
        url = f"{self._base_url()}/v1/catalog/delta"
        try:
            resp = requests.get(url, headers=self._headers(), params={'since': since}, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error("CatalogManager: error fetching delta catalog: %s", exc)
            return None

    def _apply_catalog_data(self, data: dict) -> None:
        tracks_raw = data.get('tracks', [])
        version = int(data.get('version', 0))

        batch = []
        for t in tracks_raw:
            fp_list = t.get('fingerprint', [])
            fp_bytes = CatalogStore.encode_fp(fp_list) if fp_list else b''
            batch.append({
                'id': int(t['id']),
                'artista': t.get('artista', ''),
                'titulo': t.get('titulo', ''),
                'isrc': t.get('isrc', ''),
                'duration_seg': float(t.get('duration_seg', 0)),
                'fp_raw': fp_bytes,
                'active': 1 if t.get('active', True) else 0,
                'updated_at': int(t.get('updated_at', 0)),
                'is_promovida': 1 if t.get('is_promovida', False) else 0,
            })

        if batch:
            self._store.upsert_batch(batch)

        self._store.local_version = version
        self._store.last_sync = version

        logger.info(
            "CatalogManager: applied %d tracks, version=%d", len(batch), version
        )

        # Reload matcher with fresh data
        self._matcher.reload(self._store.load_all())

    def _sync(self) -> None:
        server_version = self._get_server_version()
        if server_version is None:
            logger.warning("CatalogManager: could not reach server, skipping sync")
            return

        local_version = self._store.local_version
        track_count = self._store.track_count

        logger.info(
            "CatalogManager: local_version=%d server_version=%d track_count=%d",
            local_version, server_version, track_count,
        )

        if track_count == 0:
            # No local catalog - download full
            logger.info("CatalogManager: no local catalog, downloading full")
            data = self._fetch_full()
            if data:
                self._apply_catalog_data(data)
        elif server_version != local_version:
            # Version mismatch - download delta since last_sync
            last_sync = self._store.last_sync
            logger.info("CatalogManager: version mismatch, downloading delta since %d", last_sync)
            data = self._fetch_delta(last_sync)
            if data:
                self._apply_catalog_data(data)
        else:
            logger.info("CatalogManager: catalog is up to date")
