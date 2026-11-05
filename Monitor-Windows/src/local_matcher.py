import logging
import threading
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class LocalMatcher:
    threshold: float = 0.60      # WASAPI loopback vs MP3 — slight compression diff
    min_query_len: int = 20      # minimum FP values to attempt a match

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._index: list[dict[str, Any]] = []
        self._index_promovidas: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reload(self, entries: list[dict[str, Any]]) -> None:
        """Rebuild the in-memory index from catalog entries."""
        all_entries = [e for e in entries if e.get('fp')]
        promovidas = [e for e in all_entries if e.get('is_promovida')]

        # Pre-convert FP lists to numpy arrays for fast matching
        for e in all_entries:
            fp = e.get('fp', [])
            if isinstance(fp, list):
                # Chromaprint values are signed int32; reinterpret bits as uint32
                e['_fp_np'] = np.array(fp, dtype=np.int32).view(np.uint32)
            elif isinstance(fp, np.ndarray):
                e['_fp_np'] = fp.astype(np.int32).view(np.uint32)
            else:
                e['_fp_np'] = np.array([], dtype=np.uint32)

        with self._lock:
            self._index = all_entries
            self._index_promovidas = promovidas

        logger.info(
            "LocalMatcher: loaded %d tracks (%d promovidas)",
            len(all_entries), len(promovidas),
        )

    def match(self, query: list[int]) -> dict[str, Any] | None:
        """Try to match query fingerprint against local catalog."""
        if not query or len(query) < self.min_query_len:
            return None

        q_np = np.array(query, dtype=np.int32).view(np.uint32)

        with self._lock:
            index_copy = list(self._index)
            promovidas_copy = list(self._index_promovidas)

        # Phase 1: promovidas first (fast — typically ≤10 tracks)
        if promovidas_copy:
            result = self._search_numpy(q_np, promovidas_copy, label="promovidas")
            if result is not None:
                return result

        # Phase 2: full index (vectorized numpy — fast even at 4520 tracks)
        return self._search_numpy(q_np, index_copy, label="full")

    # ------------------------------------------------------------------
    # Vectorized numpy search
    # ------------------------------------------------------------------

    def _search_numpy(
        self,
        query: np.ndarray,
        entries: list[dict[str, Any]],
        label: str,
    ) -> dict[str, Any] | None:
        """Slide query over each reference fingerprint using numpy XOR + popcount.

        ~100× faster than pure Python, releases the GIL during C ops so the
        UI thread stays responsive.
        """
        q_len = len(query)
        total_bits = q_len * 32

        best_score = 0.0
        best_entry: dict[str, Any] | None = None
        top_scores: list[tuple[float, str]] = []  # diagnostics

        for entry in entries:
            ref = entry.get('_fp_np')
            if ref is None or len(ref) < q_len:
                continue

            score = self._best_score_numpy(query, ref, q_len, total_bits)

            # Track top-3 regardless of threshold
            name = f"{entry.get('artista', '')} - {entry.get('titulo', '')}"
            if len(top_scores) < 3 or score > top_scores[-1][0]:
                top_scores.append((score, name))
                top_scores.sort(key=lambda x: x[0], reverse=True)
                top_scores = top_scores[:3]

            if score >= self.threshold and score > best_score:
                best_score = score
                best_entry = entry

        if best_entry is None:
            if top_scores and top_scores[0][0] > 0.30:
                top_str = ", ".join(f"{s:.3f}={n[:35]}" for s, n in top_scores)
                logger.info(
                    "LocalMatcher [%s]: no match (threshold=%.2f). Top: %s",
                    label, self.threshold, top_str,
                )
            return None

        logger.info(
            "LocalMatcher [%s]: matched '%s - %s' score=%.3f",
            label,
            best_entry.get('artista', ''),
            best_entry.get('titulo', ''),
            best_score,
        )
        return {
            'id':           best_entry.get('id'),
            'artista':      best_entry.get('artista', ''),
            'titulo':       best_entry.get('titulo', ''),
            'isrc':         best_entry.get('isrc', ''),
            'duration_seg': best_entry.get('duration_seg', 0.0),
            'score':        best_score,
            'in_catalog':   True,
            'is_promovida': bool(best_entry.get('is_promovida')),
        }

    @staticmethod
    def _best_score_numpy(
        query: np.ndarray,
        ref: np.ndarray,
        q_len: int,
        total_bits: int,
    ) -> float:
        """Return the best sliding-window Hamming similarity score using numpy."""
        r_len = len(ref)
        max_offset = r_len - q_len

        # Step size: coarser for long queries (trade precision for speed)
        step = max(1, q_len // 16) if q_len > 60 else 1

        best_score = 0.0

        for offset in range(0, max_offset + 1, step):
            xor = query ^ ref[offset: offset + q_len]
            # popcount via unpackbits (uint8 view of uint32 array)
            bit_count = int(np.unpackbits(xor.view(np.uint8)).sum())
            score = 1.0 - bit_count / total_bits
            if score > best_score:
                best_score = score
            if best_score > 0.92:
                break

        return best_score
