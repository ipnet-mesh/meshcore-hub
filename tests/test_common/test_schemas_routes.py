"""Tests for route schema validators (RouteUpdate, RoutePreviewRequest)."""

import pytest
from pydantic import ValidationError

from meshcore_hub.common.schemas.routes import RoutePreviewRequest, RouteUpdate


class TestRouteUpdateValidator:
    def test_min_two_nodes(self):
        with pytest.raises(ValidationError, match="At least 2 path nodes"):
            RouteUpdate(node_public_keys=["a" * 64])

    def test_distinct_nodes(self):
        with pytest.raises(ValidationError, match="Path nodes must be distinct"):
            RouteUpdate(node_public_keys=["a" * 64, "a" * 64])

    def test_clear_threshold_must_exceed_packet_count(self):
        with pytest.raises(ValidationError, match="clear_threshold must be >"):
            RouteUpdate(packet_count_threshold=5, clear_threshold=5)

    def test_clear_threshold_ok_when_only_one_set(self):
        route = RouteUpdate(clear_threshold=5)
        assert route.clear_threshold == 5

    def test_clear_threshold_gt_packet_count_ok(self):
        route = RouteUpdate(packet_count_threshold=3, clear_threshold=6)
        assert route.clear_threshold == 6


class TestRoutePreviewValidator:
    def test_distinct_nodes(self):
        with pytest.raises(ValidationError, match="Path nodes must be distinct"):
            RoutePreviewRequest(node_public_keys=["a" * 64, "a" * 64])

    def test_min_two_nodes(self):
        with pytest.raises(ValidationError, match="At least 2 path nodes"):
            RoutePreviewRequest(node_public_keys=["a" * 64])
