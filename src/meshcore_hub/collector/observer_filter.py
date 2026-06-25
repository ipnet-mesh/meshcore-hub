"""Allow/deny filtering of observer-sourced events by observer public key.

Remote observers identify themselves via the public-key segment of their
LetsMesh upload topic (``<prefix>/<iata>/<public_key>/<feed>``). This module
decides whether a given observer's events should be ingested, based on operator-
configured allow/deny lists.

Matching is case-insensitive prefix matching: an observer key matches a list
entry when the (lower-cased) key starts with the (lower-cased, trimmed) entry,
so operators may use full 64-char keys or shorter prefixes. The allowlist takes
precedence over the denylist.
"""

from __future__ import annotations

from dataclasses import dataclass


def _normalise(entries: list[str] | None) -> tuple[str, ...]:
    """Lower-case, strip, and drop empty entries."""
    if not entries:
        return ()
    return tuple(e.strip().lower() for e in entries if e and e.strip())


@dataclass(frozen=True)
class ObserverFilter:
    """Decides whether an observer's events should be ingested.

    Allowlist takes precedence over denylist. Matching is case-insensitive
    prefix matching against the observer public key.
    """

    allowlist: tuple[str, ...] = ()
    denylist: tuple[str, ...] = ()

    @classmethod
    def from_lists(
        cls,
        allowlist: list[str] | None = None,
        denylist: list[str] | None = None,
    ) -> "ObserverFilter":
        """Build a filter from raw (un-normalised) allow/deny entry lists."""
        return cls(allowlist=_normalise(allowlist), denylist=_normalise(denylist))

    @property
    def active(self) -> bool:
        """True when either list is non-empty (i.e. filtering is in effect)."""
        return bool(self.allowlist or self.denylist)

    def is_allowed(self, public_key: str | None) -> bool:
        """Return whether the given observer public key may ingest events.

        - Both lists empty: allow everything (default behaviour).
        - Allowlist non-empty: allow only keys matching an allowlist entry
          (the denylist is ignored).
        - Allowlist empty, denylist non-empty: allow unless the key matches a
          denylist entry.
        """
        if not self.allowlist and not self.denylist:
            return True
        key = (public_key or "").strip().lower()
        if self.allowlist:
            return any(key.startswith(entry) for entry in self.allowlist)
        return not any(key.startswith(entry) for entry in self.denylist)
