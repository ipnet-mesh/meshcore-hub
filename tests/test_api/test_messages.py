"""Tests for message API routes."""


class TestListMessages:
    """Tests for GET /messages endpoint."""

    def test_list_messages_empty(self, client_no_auth):
        """Test listing messages when database is empty."""
        response = client_no_auth.get("/api/v1/messages")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_messages_with_data(self, client_no_auth, sample_message):
        """Test listing messages with data in database."""
        response = client_no_auth.get("/api/v1/messages")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] == 1
        assert data["items"][0]["text"] == sample_message.text
        assert data["items"][0]["message_type"] == sample_message.message_type

    def test_list_messages_filter_by_type(self, client_no_auth, sample_message):
        """Test filtering messages by type."""
        response = client_no_auth.get("/api/v1/messages?message_type=direct")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

        response = client_no_auth.get("/api/v1/messages?message_type=channel")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0

    def test_list_messages_pagination(self, client_no_auth):
        """Test message list pagination parameters."""
        response = client_no_auth.get("/api/v1/messages?limit=25&offset=10")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 25
        assert data["offset"] == 10


class TestGetMessage:
    """Tests for GET /messages/{id} endpoint."""

    def test_get_message_success(self, client_no_auth, sample_message):
        """Test getting a specific message."""
        response = client_no_auth.get(f"/api/v1/messages/{sample_message.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["text"] == sample_message.text

    def test_get_message_not_found(self, client_no_auth):
        """Test getting a non-existent message."""
        response = client_no_auth.get("/api/v1/messages/nonexistent-id")
        assert response.status_code == 404
