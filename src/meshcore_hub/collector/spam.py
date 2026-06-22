"""Spam scoring for ingested messages.

Pure helpers (`normalize_sender`, `compute_path_prefix`) plus two DB-querying
scorers (`score_message`, `rescore_recent`) and a config object (`SpamConfig`).

The design is described in ``docs/plans/20260622-2243-spam-detection/plan.md``.
Counts are computed directly from Postgres/SQLite over the
``(path_prefix, received_at)`` and ``(sender_normalized, received_at)`` indexes;
the window cutoff is always a Python-computed datetime passed as a bound
parameter, so identical code runs on both backends (no SQL ``NOW()``/``INTERVAL``).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from meshcore_hub.common.models import Message

if TYPE_CHECKING:
    from meshcore_hub.common.config import CollectorSettings

logger = logging.getLogger(__name__)

# Trailing run of digits and/or whitespace, e.g. "bob 17" / "bob17" -> "bob".
_TRAILING_DIGITS = re.compile(r"[\s\d]+$")


@dataclass(frozen=True)
class SpamConfig:
    """Resolved spam-scoring configuration.

    Built from ``CollectorSettings`` (which inherits the shared
    ``spam_detection_enabled`` / ``spam_score_threshold`` from CommonSettings).
    """

    enabled: bool = False
    window_seconds: int = 300
    path_hops: int = 3
    min_path_hops: int = 5
    path_threshold: int = 5
    name_threshold: int = 5
    weight_path: float = 0.7
    weight_name: float = 0.3
    score_threshold: float = 0.6
    rescore_interval_seconds: int = 120

    @classmethod
    def from_settings(cls, settings: "CollectorSettings") -> "SpamConfig":
        """Build a SpamConfig from a CollectorSettings instance."""
        return cls(
            enabled=settings.spam_detection_enabled,
            window_seconds=settings.spam_window_seconds,
            path_hops=settings.spam_path_hops,
            min_path_hops=settings.spam_min_path_hops,
            path_threshold=settings.spam_path_threshold,
            name_threshold=settings.spam_name_threshold,
            weight_path=settings.spam_weight_path,
            weight_name=settings.spam_weight_name,
            score_threshold=settings.spam_score_threshold,
            rescore_interval_seconds=settings.spam_rescore_interval_seconds,
        )


@dataclass(frozen=True)
class SpamScore:
    """Result of scoring a single message, with the driving component counts."""

    score: float
    path_count: int
    name_count: int


_cached_config: Optional[SpamConfig] = None


def get_spam_config() -> SpamConfig:
    """Return the process-wide SpamConfig, built once from collector settings."""
    global _cached_config
    if _cached_config is None:
        from meshcore_hub.common.config import get_collector_settings

        _cached_config = SpamConfig.from_settings(get_collector_settings())
    return _cached_config


def reset_spam_config() -> None:
    """Clear the cached SpamConfig (used by tests after changing env)."""
    global _cached_config
    _cached_config = None


def normalize_sender(name: Optional[str]) -> Optional[str]:
    """Lower-case a sender name and strip the trailing digit/space suffix.

    ``bob17`` -> ``bob``; ``Bob 2`` -> ``bob``. Returns None for empty input or
    a name that is entirely digits/whitespace.
    """
    if not name:
        return None
    stripped = _TRAILING_DIGITS.sub("", name.strip())
    stripped = stripped.strip().lower()
    return stripped or None


def compute_path_prefix(path_hashes: Optional[list[str]], hops: int) -> Optional[str]:
    """Join the first ``hops`` origin-side hop hashes into a stable prefix key.

    Returns None when there is no path or ``hops`` is non-positive.
    """
    if not path_hashes or hops <= 0:
        return None
    prefix = ",".join(path_hashes[:hops])
    return prefix or None


def _count(
    session: Session,
    *,
    sender_normalized: str,
    path_prefix: Optional[str],
    lo: datetime,
    hi: Optional[datetime],
    exclude_id: Optional[str],
) -> int:
    """Count messages in ``[lo, hi]`` matching sender (and path when given)."""
    stmt = (
        select(func.count())
        .select_from(Message)
        .where(Message.sender_normalized == sender_normalized)
        .where(Message.received_at >= lo)
    )
    if path_prefix is not None:
        stmt = stmt.where(Message.path_prefix == path_prefix)
    if hi is not None:
        stmt = stmt.where(Message.received_at <= hi)
    if exclude_id is not None:
        stmt = stmt.where(Message.id != exclude_id)
    return int(session.execute(stmt).scalar() or 0)


def _combine(
    *, path_count: int, name_count: int, path_eligible: bool, cfg: SpamConfig
) -> float:
    """Combine the windowed counts into a 0.0-1.0 score.

    The score is a weighted average over the signals that are actually
    *available*, normalised by the active weight. When both signals are present
    and the weights sum to 1.0 (the default), this is the plain
    ``w_path*path + w_name*name`` blend.

    The key case: when the path signal is gated off — a short/zero-hop path or no
    path data at all, e.g. an observer sitting right next to the sender — the name
    signal stands on its own at *full* weight. Otherwise name-only spam (rotating
    ``bob1``/``bob2``) would be capped at ``weight_name`` (0.3 by default) and
    could never cross the threshold, leaving local/zero-hop spam undetectable.
    """
    name_thr = max(cfg.name_threshold, 1)
    name_term = min(name_count / name_thr, 1.0)

    if not path_eligible:
        # Name signal is the only evidence available; trust it fully.
        return min(1.0, name_term)

    path_thr = max(cfg.path_threshold, 1)
    path_term = min(path_count / path_thr, 1.0)
    total_weight = cfg.weight_path + cfg.weight_name
    if total_weight <= 0:
        return 0.0
    score = (cfg.weight_path * path_term + cfg.weight_name * name_term) / total_weight
    return min(1.0, score)


def score_message(
    session: Session,
    *,
    path_prefix: Optional[str],
    sender_normalized: Optional[str],
    path_len: Optional[int],
    received_at: datetime,
    cfg: SpamConfig,
) -> SpamScore:
    """Online spam score for a message about to be inserted.

    Counts only prior rows (those already in the window before ``received_at``),
    so a first-ever message scores 0. The path signal is the joint
    ``(path_prefix, sender_normalized)`` count and is only applied when the path
    is at/above the ``min_path_hops`` gate; otherwise scoring relies on the name
    signal alone.
    """
    if sender_normalized is None:
        return SpamScore(score=0.0, path_count=0, name_count=0)

    cutoff = received_at - timedelta(seconds=cfg.window_seconds)
    path_eligible = (
        path_prefix is not None
        and path_len is not None
        and path_len >= cfg.min_path_hops
    )

    path_count = 0
    if path_eligible:
        path_count = _count(
            session,
            sender_normalized=sender_normalized,
            path_prefix=path_prefix,
            lo=cutoff,
            hi=None,
            exclude_id=None,
        )
    name_count = _count(
        session,
        sender_normalized=sender_normalized,
        path_prefix=None,
        lo=cutoff,
        hi=None,
        exclude_id=None,
    )

    score = _combine(
        path_count=path_count,
        name_count=name_count,
        path_eligible=path_eligible,
        cfg=cfg,
    )
    return SpamScore(score=score, path_count=path_count, name_count=name_count)


def rescore_recent(
    session: Session,
    cfg: SpamConfig,
    now: Optional[datetime] = None,
) -> int:
    """Recompute scores for recent rows with hindsight (symmetric window).

    Unlike the online score, this counts peers on *both* sides of each row
    (``|other.received_at - row.received_at| <= window``), so it catches the
    leading edge of a burst that the online score necessarily missed. Only rows
    whose score actually changes are written. Returns the number of rows updated.
    Idempotent.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    window = timedelta(seconds=cfg.window_seconds)
    # Look back a couple of windows so we re-touch rows whose hindsight peers
    # have since arrived, without rescanning the whole table.
    lookback = now - timedelta(seconds=cfg.window_seconds * 2)

    rows = (
        session.execute(select(Message).where(Message.received_at >= lookback))
        .scalars()
        .all()
    )

    updated = 0
    for row in rows:
        if row.sender_normalized is None:
            new_score = 0.0
            path_count = 0
            name_count = 0
        else:
            center = row.received_at
            lo = center - window
            hi = center + window
            path_eligible = (
                row.path_prefix is not None
                and row.path_len is not None
                and row.path_len >= cfg.min_path_hops
            )
            path_count = 0
            if path_eligible:
                path_count = _count(
                    session,
                    sender_normalized=row.sender_normalized,
                    path_prefix=row.path_prefix,
                    lo=lo,
                    hi=hi,
                    exclude_id=row.id,
                )
            name_count = _count(
                session,
                sender_normalized=row.sender_normalized,
                path_prefix=None,
                lo=lo,
                hi=hi,
                exclude_id=row.id,
            )
            new_score = _combine(
                path_count=path_count,
                name_count=name_count,
                path_eligible=path_eligible,
                cfg=cfg,
            )

        old_score = row.spam_score
        if old_score is None or abs(old_score - new_score) > 1e-9:
            logger.debug(
                "Re-scored message %s: %s -> %.2f (path_n=%d name_n=%d)",
                row.id,
                "None" if old_score is None else f"{old_score:.2f}",
                new_score,
                path_count,
                name_count,
            )
            row.spam_score = new_score
            updated += 1

    return updated
