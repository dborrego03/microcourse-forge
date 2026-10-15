from forge import mcp_server


async def test_tools_and_their_side_effect_hints():
    tools = {t.name: t for t in await mcp_server.server.list_tools()}

    assert set(tools) == {"search_sources", "generate_lesson", "evaluate_lesson", "export_package"}
    assert tools["search_sources"].annotations.read_only_hint is True
    assert tools["export_package"].annotations.read_only_hint is False
    assert tools["generate_lesson"].input_schema["required"] == ["topic"]


async def test_search_sources_returns_citable_passages(monkeypatch):
    class FakeConn:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    async def fake_connect():
        return FakeConn()

    async def fake_search(conn, query, k):
        assert k == 10  # clamped
        return [{"id": 3, "section_path": "6 Learning > 6.2", "pdf_page_start": 195, "pdf_page_end": 196,
                 "text": "Pavlov...", "score": 1.2}]  # fmt: skip

    monkeypatch.setattr(mcp_server, "connect", fake_connect)
    monkeypatch.setattr(mcp_server, "rerank_search", fake_search)

    result = await mcp_server.server.call_tool("search_sources", {"query": "conditioning", "k": 50})

    assert not result.is_error
    assert result.structured_content["result"][0] == {
        "id": 3, "section": "6 Learning > 6.2", "pdf_pages": "195-196", "text": "Pavlov...",
    }  # fmt: skip
