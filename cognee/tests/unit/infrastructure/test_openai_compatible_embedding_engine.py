"""
Tests for OpenAICompatibleEmbeddingEngine.

Verifies that the engine:
- Returns mock embeddings when MOCK_EMBEDDING is set
- Calls the OpenAI SDK with encoding_format="float"
- Reports correct vector size and batch size
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestOpenAICompatibleEmbeddingEngine:
    """Unit tests for OpenAICompatibleEmbeddingEngine."""

    def _make_engine(self, **kwargs):
        """Create an engine instance with defaults suitable for testing."""
        defaults = {
            "model": "test-model",
            "dimensions": 4096,
            "max_completion_tokens": 8191,
            "endpoint": "http://localhost:8099",
            "api_key": "test-key",
            "batch_size": 36,
        }
        defaults.update(kwargs)

        from cognee.infrastructure.databases.vector.embeddings.OpenAICompatibleEmbeddingEngine import (
            OpenAICompatibleEmbeddingEngine,
        )

        return OpenAICompatibleEmbeddingEngine(**defaults)

    @pytest.mark.asyncio
    async def test_mock_embedding(self, monkeypatch):
        """When MOCK_EMBEDDING=true, embed_text returns zero vectors of correct dimensions."""
        monkeypatch.setenv("MOCK_EMBEDDING", "true")
        engine = self._make_engine(dimensions=4096)
        result = await engine.embed_text(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == 4096
        assert all(v == 0.0 for v in result[0])

    @pytest.mark.asyncio
    async def test_embed_text_calls_openai_with_encoding_format_float(self, monkeypatch):
        """embed_text must call OpenAI SDK with encoding_format='float'."""
        monkeypatch.delenv("MOCK_EMBEDDING", raising=False)

        engine = self._make_engine()

        # Build a mock response matching OpenAI SDK's CreateEmbeddingResponse
        mock_item = MagicMock()
        mock_item.embedding = [0.1] * 4096

        mock_response = MagicMock()
        mock_response.data = [mock_item]

        # Mock the AsyncOpenAI client's embeddings.create
        engine._client = MagicMock()
        engine._client.embeddings.create = AsyncMock(return_value=mock_response)

        result = await engine.embed_text(["test text"])

        # Verify create was called with encoding_format="float"
        engine._client.embeddings.create.assert_called_once_with(
            model="test-model",
            input=["test text"],
            encoding_format="float",
        )

        assert len(result) == 1
        assert len(result[0]) == 4096

    def test_get_vector_size(self):
        """get_vector_size returns the configured dimensions."""
        engine = self._make_engine(dimensions=768)
        assert engine.get_vector_size() == 768

    def test_get_batch_size(self):
        """get_batch_size returns the configured batch size."""
        engine = self._make_engine(batch_size=50)
        assert engine.get_batch_size() == 50

    def test_max_completion_tokens_is_exposed(self):
        """The engine exposes max_completion_tokens for chunk sizing logic."""
        engine = self._make_engine(max_completion_tokens=2048)
        assert engine.max_completion_tokens == 2048

    def test_endpoint_normalization(self, monkeypatch):
        """Endpoint without /v1 gets /v1 appended for the SDK base_url.

        Phase 8.4.2 platform-patch: explicitly delenv COGNEE_EMBEDDING_NO_V1 so
        this test always exercises the default normalization path regardless of
        the shell env state when pytest runs.
        """
        monkeypatch.delenv("COGNEE_EMBEDDING_NO_V1", raising=False)
        engine = self._make_engine(endpoint="http://localhost:8099")
        assert str(engine._client._base_url).rstrip("/").endswith("/v1")

        engine2 = self._make_engine(endpoint="http://localhost:8099/v1")
        assert str(engine2._client._base_url).rstrip("/").endswith("/v1")

        # Both should produce equivalent normalized URLs
        assert str(engine._client._base_url) == str(engine2._client._base_url)

    def test_endpoint_normalization_strips_embeddings_suffix(self, monkeypatch):
        """Endpoint with /v1/embeddings should not produce /v1/embeddings/v1.

        Phase 8.4.2 platform-patch: same delenv discipline as above.
        """
        monkeypatch.delenv("COGNEE_EMBEDDING_NO_V1", raising=False)
        engine = self._make_engine(endpoint="http://localhost:8099/v1/embeddings")
        base_url = str(engine._client._base_url).rstrip("/")
        assert base_url.endswith("/v1")
        assert "/embeddings" not in base_url

    def test_endpoint_normalization_no_v1_true(self, monkeypatch):
        """PLATFORM-PATCH (gamemagick 2026-05-24): COGNEE_EMBEDDING_NO_V1=true
        bypasses the /v1 normalization. Endpoint passed through as-is so the
        openai SDK POSTs to {base}/embeddings without the /v1 prefix.

        Use case: infinity-emb 0.0.77 serves /embeddings (no /v1).
        """
        monkeypatch.setenv("COGNEE_EMBEDDING_NO_V1", "true")
        engine = self._make_engine(endpoint="http://infinity.local:9303")
        # Base URL is the endpoint as-is (no /v1 appended). openai SDK still
        # appends /embeddings to this base when calling embeddings.create.
        base_url = str(engine._client._base_url).rstrip("/")
        assert base_url == "http://infinity.local:9303", (
            f"Expected base_url 'http://infinity.local:9303' (no /v1 appended); "
            f"got: {base_url!r}"
        )

    def test_endpoint_normalization_no_v1_strips_trailing_v1(self, monkeypatch):
        """PLATFORM-PATCH (gamemagick 2026-05-24) CON-5 guard: when
        COGNEE_EMBEDDING_NO_V1=true AND EMBEDDING_ENDPOINT accidentally ends
        with /v1, strip the trailing /v1 so the openai SDK doesn't silently
        produce /v1/embeddings against a server that serves /embeddings.
        """
        monkeypatch.setenv("COGNEE_EMBEDDING_NO_V1", "true")
        engine = self._make_engine(endpoint="http://infinity.local:9303/v1")
        base_url = str(engine._client._base_url).rstrip("/")
        assert base_url == "http://infinity.local:9303", (
            f"Expected trailing /v1 stripped to 'http://infinity.local:9303'; "
            f"got: {base_url!r}"
        )
