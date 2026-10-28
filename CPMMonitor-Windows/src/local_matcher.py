import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class LocalMatcher:
    threshold: float = 0.70
    half_threshold: float = 0.62
    gap_tolerance_factor: int = 2

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._index: list[dict[str, Any]] = []
        self._index_promovidas: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reload(self, entries: list[dict[str, Any]]) -> None:
        """Rebuild the in-memory index from catalog entries.

        Each entry dict is expected to have keys:
            id, artista, titulo, isrc, duration_seg, fp (list[int]),
            active, updated_at, is_promovida
        """
        all_entries = [e for e in entries if e.get('fp')]
        promovidas = [e for e in all_entries if e.get('is_promovida')]

        with self._lock:
            self._index = all_entries
            self._index_promovidas = promovidas

        logger.info(
            "LocalMatcher: loaded %d tracks (%d promovidas)",
            len(all_entries), len(promovidas),
        )

    def match(self, query: list[int]) -> dict[str, Any] | None:
        """Try to match query fingerprint against local catalog.

        Returns a result dict or None.
        """
        if not query:
            return None

        with self._lock:
            index_copy = list(self._index)
            promovidas_copy = list(self._index_promovidas)

        # Phase 1: check promovidas first
        if promovidas_copy:
            result = self._search_in_index(query, promovidas_copy, label="promovidas")
            if result is not None:
                return result

        # Phase 2: check full index
        return self._search_in_index(query, index_copy, label="full")

    # ------------------------------------------------------------------
    # Internal search
    # ------------------------------------------------------------------

    def _search_in_index(
        self,
        query: list[int],
        entries: list[dict[str, Any]],
        label: str,
    ) -> dict[str, Any] | None:
        best_score = 0.0
        best_entry: dict[str, Any] | None = None

        for entry in entries:
            ref = entry.get('fp', [])
            if not ref:
                continue

            score, _offset = self._sliding_score_and_offset(query, ref)

            if score < self.threshold:
                continue

            if not self._positional_consistency(query, ref):
                continue

            if score > best_score:
                best_score = score
                best_entry = entry

        if best_entry is None:
            return None

        logger.debug(
            "LocalMatcher [%s]: matched '%s - %s' score=%.3f",
            label,
            best_entry.get('artista', ''),
            best_entry.get('titulo', ''),
            best_score,
        )

        return {
            'id': best_entry.get('id'),
            'artista': best_entry.get('artista', ''),
            'titulo': best_entry.get('titulo', ''),
            'isrc': best_entry.get('isrc', ''),
            'duration_seg': best_entry.get('duration_seg', 0.0),
            'score': best_score,
            'in_catalog': True,
            'is_promovida': bool(best_entry.get('is_promovida')),
        }

    # ------------------------------------------------------------------
    # Sliding-window Hamming score
    # ------------------------------------------------------------------

    def _sliding_score_and_offset(
        self, query: list[int], ref: list[int]
    ) -> tuple[float, int]:
        """Slide query over ref and return (best_score, best_offset).

        score = 1 - popcount(XOR) / (len(query) * 32)
        """
        q_len = len(query)
        r_len = len(ref)

        if q_len == 0 or r_len == 0:
            return 0.0, 0

        # If query is longer than ref, we slide ref over query instead
        if q_len > r_len:
            score, offset = self._sliding_score_and_offset(ref, query)
            return score, -offset

        # step size: 1 for short queries, larger for long ones
        step = 1 if q_len <= 120 else max(1, q_len // 8)

        max_offset = r_len - q_len
        best_score = 0.0
        best_offset = 0
        total_bits = q_len * 32

        offset = 0
        while offset <= max_offset:
            xor_sum = 0
            for i in range(q_len):
                xor_val = query[i] ^ ref[offset + i]
                xor_sum += bin(xor_val).count('1')

            score = 1.0 - xor_sum / total_bits

            if score > best_score:
                best_score = score
                best_offset = offset

            # Early exit on very high score
            if best_score > 0.92:
                break

            offset += step

        return best_score, best_offset

    # ------------------------------------------------------------------
    # Positional consistency check
    # ------------------------------------------------------------------

    def _positional_consistency(
        self, query: list[int], ref: list[int]
    ) -> bool:
        """Check that both halves of the query align consistently with ref.

        Splits query in half and verifies:
        - Both halves score >= half_threshold
        - |off2 - off1 - half_len| <= half_len // gap_tolerance_factor
        """
        q_len = len(query)
        if q_len < 4:
            # Too short to split meaningfully
            return True

        half = q_len // 2
        first_half = query[:half]
        second_half = query[half:]

        score1, off1 = self._sliding_score_and_offset(first_half, ref)
        score2, off2 = self._sliding_score_and_offset(second_half, ref)

        if score1 < self.half_threshold or score2 < self.half_threshold:
            return False

        gap_tolerance = half // self.gap_tolerance_factor
        expected_gap = half
        actual_gap = abs(off2 - off1 - expected_gap)

        return actual_gap <= gap_tolerance
