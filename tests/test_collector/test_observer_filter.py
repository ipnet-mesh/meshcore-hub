"""Unit tests for the observer allow/deny ingestion filter."""

from meshcore_hub.collector.observer_filter import ObserverFilter

FULL_KEY = "F4762185BBB684510B2E3D41568300869DB5E75B284448145475F7708C1EF408"
OTHER_KEY = "A1B2C3D4E5F60718293A4B5C6D7E8F90112233445566778899AABBCCDDEEFF00"


class TestObserverFilterDefaults:
    def test_no_lists_allows_everything(self):
        f = ObserverFilter()
        assert f.active is False
        assert f.is_allowed(FULL_KEY) is True
        assert f.is_allowed(OTHER_KEY) is True

    def test_from_lists_with_none_is_inactive(self):
        f = ObserverFilter.from_lists(None, None)
        assert f.active is False
        assert f.is_allowed(FULL_KEY) is True

    def test_from_lists_with_empty_lists_is_inactive(self):
        f = ObserverFilter.from_lists([], [])
        assert f.active is False
        assert f.is_allowed(FULL_KEY) is True


class TestAllowlist:
    def test_allows_listed_key_blocks_others(self):
        f = ObserverFilter.from_lists(allowlist=[FULL_KEY])
        assert f.active is True
        assert f.is_allowed(FULL_KEY) is True
        assert f.is_allowed(OTHER_KEY) is False

    def test_allowlist_takes_precedence_over_denylist(self):
        # Same key is both allowed and denied -> allowlist wins (key allowed).
        f = ObserverFilter.from_lists(allowlist=[FULL_KEY], denylist=[FULL_KEY])
        assert f.is_allowed(FULL_KEY) is True

    def test_allowlist_present_means_unlisted_denied_regardless_of_denylist(self):
        f = ObserverFilter.from_lists(allowlist=[FULL_KEY], denylist=[OTHER_KEY])
        # OTHER_KEY is not on the allowlist, so it is blocked even though the
        # denylist is effectively ignored.
        assert f.is_allowed(OTHER_KEY) is False


class TestDenylist:
    def test_blocks_listed_key_allows_others(self):
        f = ObserverFilter.from_lists(denylist=[FULL_KEY])
        assert f.active is True
        assert f.is_allowed(FULL_KEY) is False
        assert f.is_allowed(OTHER_KEY) is True


class TestCaseInsensitivity:
    def test_lowercase_entry_matches_uppercase_key(self):
        f = ObserverFilter.from_lists(denylist=[FULL_KEY.lower()])
        assert f.is_allowed(FULL_KEY) is False

    def test_uppercase_entry_matches_lowercase_key(self):
        f = ObserverFilter.from_lists(denylist=[FULL_KEY.upper()])
        assert f.is_allowed(FULL_KEY.lower()) is False


class TestPrefixMatching:
    def test_short_prefix_matches_full_key(self):
        f = ObserverFilter.from_lists(denylist=["F4762185"])
        assert f.is_allowed(FULL_KEY) is False
        assert f.is_allowed(OTHER_KEY) is True

    def test_non_matching_prefix_does_not_match(self):
        f = ObserverFilter.from_lists(denylist=["DEADBEEF"])
        assert f.is_allowed(FULL_KEY) is True

    def test_allowlist_prefix(self):
        f = ObserverFilter.from_lists(allowlist=["f4762185"])
        assert f.is_allowed(FULL_KEY) is True
        assert f.is_allowed(OTHER_KEY) is False


class TestHygiene:
    def test_whitespace_and_empty_entries_dropped(self):
        f = ObserverFilter.from_lists(denylist=["  ", "", FULL_KEY + "  "])
        # The blank/whitespace entries must not turn into a match-everything
        # prefix; only the real (trimmed) key is in effect.
        assert f.is_allowed(OTHER_KEY) is True
        assert f.is_allowed(FULL_KEY) is False

    def test_all_blank_entries_yield_inactive_filter(self):
        f = ObserverFilter.from_lists(allowlist=["", "  "], denylist=["  "])
        assert f.active is False
        assert f.is_allowed(FULL_KEY) is True

    def test_none_public_key_against_active_filter(self):
        # A missing key never matches a real allowlist entry -> denied.
        allow = ObserverFilter.from_lists(allowlist=[FULL_KEY])
        assert allow.is_allowed(None) is False
        # ... and is not on a denylist -> allowed.
        deny = ObserverFilter.from_lists(denylist=[FULL_KEY])
        assert deny.is_allowed(None) is True
