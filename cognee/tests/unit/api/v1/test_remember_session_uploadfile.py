"""V2-6 (gamemagick 2026-05-31) — tests for _data_to_text_async + _add_to_session
UploadFile handling. Locks the PLATFORM-PATCH that lets POST /v1/remember
actually persist session-cache writes when the payload is a multipart
text upload (the cognee-mcp wrapper's _text_upload path).

See PLATFORM_PATCHES.md row for cognee/api/v1/remember/remember.py.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from cognee.api.v1.remember.remember import (
    _add_to_session,
    _data_to_text_async,
)


def _user(id_: str = "u-default"):
    return SimpleNamespace(id=id_)


class _FakeUploadFile:
    """Minimal UploadFile stand-in with async .read() and async .seek()."""

    def __init__(self, content: bytes, name: str = "data"):
        self._content = content
        self.name = name
        self._pos = 0

    async def read(self) -> bytes:
        return self._content

    async def seek(self, offset: int) -> None:
        self._pos = offset


class _ReadFailUploadFile:
    """UploadFile-like whose .read() raises."""

    def __init__(self, name: str = "data"):
        self.name = name

    async def read(self) -> bytes:
        raise IOError("simulated read failure")

    async def seek(self, offset: int) -> None:
        pass


@pytest.mark.asyncio
async def test_data_to_text_async_handles_uploadfile_list():
    """List[UploadFile] with bytes content should decode to the text payload,
    NOT a "[file: ...]" / "[UploadFile]" placeholder."""
    upload = _FakeUploadFile(b"V26-PROBE-MARKER-CONTENT", name="data")
    result = await _data_to_text_async([upload])
    assert result == "V26-PROBE-MARKER-CONTENT"
    assert "[file:" not in result
    assert "[UploadFile]" not in result


@pytest.mark.asyncio
async def test_data_to_text_async_handles_single_uploadfile():
    """A single (non-list) UploadFile should also decode to its content."""
    upload = _FakeUploadFile(b"single-file-content", name="data")
    result = await _data_to_text_async(upload)
    assert result == "single-file-content"


@pytest.mark.asyncio
async def test_data_to_text_async_falls_back_to_placeholder_on_read_failure():
    """When UploadFile.read() raises, fall back to the sync _data_to_text
    placeholder string. This preserves the silent-skip behaviour for genuinely
    broken uploads (matches _SESSION_PLACEHOLDER_PREFIXES)."""
    upload = _ReadFailUploadFile(name="data")
    result = await _data_to_text_async([upload])
    assert result == "[file: data]"


@pytest.mark.asyncio
async def test_add_to_session_writes_qa_entry_for_uploadfile_data():
    """The end-to-end V2-6 lock: _add_to_session called with List[UploadFile]
    payload (the HTTP API path) must invoke sm.add_qa(answer=<content>) — NOT
    silently skip via the placeholder check."""
    upload = _FakeUploadFile(b"DATA-FROM-REMEMBER", name="data")
    user = _user("u-1")

    sm = SimpleNamespace()
    sm.is_available = True
    sm.add_qa = AsyncMock(return_value="qa-id-1")

    with patch(
        "cognee.api.v1.remember.remember.get_session_manager",
        return_value=sm,
    ):
        await _add_to_session("session-1", [upload], user)

    sm.add_qa.assert_awaited_once()
    call_kwargs = sm.add_qa.await_args.kwargs
    assert call_kwargs["user_id"] == "u-1"
    assert call_kwargs["session_id"] == "session-1"
    assert call_kwargs["question"] == ""
    assert call_kwargs["context"] == ""
    assert call_kwargs["answer"] == "DATA-FROM-REMEMBER"


@pytest.mark.asyncio
async def test_add_to_session_still_skips_pure_string_placeholder():
    """Regression guard: string-only placeholder inputs (e.g. someone
    explicitly passing "[UploadFile]") MUST still trigger the silent skip
    — V2-6 only fixes the *upload-content-readable* case, not the
    placeholder-string case."""
    user = _user("u-2")

    sm = SimpleNamespace()
    sm.is_available = True
    sm.add_qa = AsyncMock(return_value=None)

    with patch(
        "cognee.api.v1.remember.remember.get_session_manager",
        return_value=sm,
    ):
        # String "[UploadFile]" matches _SESSION_PLACEHOLDER_PREFIXES.
        await _add_to_session("session-2", "[UploadFile]", user)

    sm.add_qa.assert_not_awaited()
