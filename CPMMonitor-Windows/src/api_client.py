import logging
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 20  # seconds


class APIClient:
    def __init__(self, config) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {'X-API-Key': self._config.api_key}

    def _base_url(self) -> str:
        return self._config.server_url.rstrip('/')

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_plays(self, plays: list[dict[str, Any]]) -> bool:
        """POST /v1/plays with a batch of play records.

        Body: {"plays": [...]}
        Returns True on HTTP 2xx, False otherwise.
        """
        url = f"{self._base_url()}/v1/plays"
        payload = {"plays": plays}

        try:
            resp = requests.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code >= 200 and resp.status_code < 300:
                logger.info("APIClient.send_plays: sent %d plays, status=%d", len(plays), resp.status_code)
                return True
            else:
                logger.warning(
                    "APIClient.send_plays: unexpected status=%d body=%s",
                    resp.status_code,
                    resp.text[:200],
                )
                return False
        except requests.exceptions.Timeout:
            logger.error("APIClient.send_plays: request timed out")
            return False
        except Exception as exc:
            logger.error("APIClient.send_plays error: %s", exc, exc_info=True)
            return False

    def verify_venue(
        self,
        venue_id: str,
        api_key: str,
        server_url: str,
    ) -> Optional[dict[str, Any]]:
        """GET /v1/venue/{venue_id} to verify credentials.

        Returns {"ok": true, "nombre_local": "Bar X"} or None.
        """
        base = server_url.rstrip('/')
        url = f"{base}/v1/venue/{venue_id}"
        headers = {'X-API-Key': api_key}

        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            if resp.status_code >= 200 and resp.status_code < 300:
                data = resp.json()
                return data
            elif resp.status_code == 401 or resp.status_code == 403:
                logger.warning("APIClient.verify_venue: unauthorized (status=%d)", resp.status_code)
                return None
            elif resp.status_code == 404:
                logger.warning("APIClient.verify_venue: venue not found")
                return None
            else:
                logger.warning("APIClient.verify_venue: unexpected status=%d", resp.status_code)
                return None
        except requests.exceptions.Timeout:
            logger.error("APIClient.verify_venue: request timed out")
            return None
        except Exception as exc:
            logger.error("APIClient.verify_venue error: %s", exc, exc_info=True)
            return None
