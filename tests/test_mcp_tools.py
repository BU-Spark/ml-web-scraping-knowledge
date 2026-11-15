"""Synthetic contract, query, and actual MCP HTTP tests; no shared DB or model download."""
import asyncio
from contextlib import contextmanager
from unittest.mock import Mock, patch

import httpx
import pytest

from database import queries
from mcp_server import tools
from mcp_server.filters import allowed_visibility, literal_pattern
from mcp_server.retrieval import RetrievalService
from mcp_server.server import create_server

VECTOR = [1.0] + [0.0] * 383


def unit(**overrides):
    row = dict(unit_id="ku-test", chunk_id="sem-test", doc_id="doc-test", section_id=0,
               claim="Identify the economic buyer before qualification.",
               evidence_quote="Identify the economic buyer", level="know_how", unit_type="how_to",
               context={"who": "account executive"}, category="Sales Methodology and Process",
               visibility="internal", sensitivity="confidential", tags=["INFERRED"],
               source_file="invented.txt", source_url=None, doc_title="Synthetic guide",
               source_text="Identify the economic buyer before qualification.",
               chunk_char_start=0, chunk_char_end=49)
    row.update(overrides)
    return row


@contextmanager
def connection():
    yield object()


def test_category_tools_use_schema_names_and_filters():
    with patch.object(tools, "service") as service:
        for function, category in ((tools.get_sales_methodology, "Sales Methodology and Process"),
                                   (tools.get_segmentation_guidance, "Segmentation and Territory"),
                                   (tools.get_enablement_practices, "Enablement Operations")):
            function("How?", entity="MEDDIC", company_size="SMB", limit=3)
            assert service.search.call_args.kwargs["category"] == category
            assert service.search.call_args.kwargs["entity"] == "MEDDIC"
            assert service.search.call_args.kwargs["company_size"] == "SMB"


def test_retrieval_preserves_internal_citations_and_uses_view_policy(monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_VISIBILITY", "public")
    embed = Mock(return_value=[VECTOR])
    service = RetrievalService(connection, embed)
    with patch.object(queries, "search", return_value=[unit()]) as search:
        response = service.search("Buyer qualification", entity="MEDDICC", role="AE")
    assert search.call_args.kwargs["visibility"] == ("public",)
    assert search.call_args.kwargs["entities"] == ("meddic", "meddicc")
    assert search.call_args.kwargs["context"] == {"who": "AE"}
    result = response["results"][0]
    assert result["sensitivity"] == "confidential"
    assert result["tags"] == ["INFERRED"]
    assert result["citation"]["source_file"] == "invented.txt"
    assert result["citation"]["url"] is None
    assert "embedding" not in result


def test_source_never_embeds_and_returns_actual_chunk():
    embed = Mock(side_effect=AssertionError("No embedding needed"))
    with patch.object(queries, "sources", return_value=[unit()]):
        response = RetrievalService(connection, embed).source("ku-test")
    embed.assert_not_called()
    assert response["results"][0]["source_passage"]["text"] == unit()["source_text"]


def test_empty_search_is_explained():
    with patch.object(queries, "search", return_value=[]):
        response = RetrievalService(connection, lambda _: [VECTOR]).search("Nothing")
    assert response["status"] == "no_results"
    assert response["message"] and not response["results"]


@pytest.mark.parametrize("kwargs", [{"query": " "}, {"query": "x", "limit": 0},
                                      {"query": "x", "limit": True},
                                      {"query": "x", "category": "1"}])
def test_invalid_inputs_fail_before_model_or_database(kwargs):
    embed = Mock()
    with pytest.raises(ValueError):
        RetrievalService(connection, embed).search(**kwargs)
    embed.assert_not_called()


def test_errors_do_not_disclose_secrets_or_passages(caplog):
    def broken():
        raise RuntimeError("postgresql://secret synthetic confidential passage")
    with pytest.raises(RuntimeError) as error:
        RetrievalService(broken, lambda _: [VECTOR]).search("test")
    assert "secret" not in str(error.value) + caplog.text
    assert "confidential passage" not in str(error.value) + caplog.text


def test_visibility_policy_fails_closed(monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_VISIBILITY", "public,typo")
    with pytest.raises(ValueError):
        allowed_visibility()


class Cursor:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, sql, params):
        self.sql, self.params = sql, params

    def fetchall(self):
        return []


class Connection:
    def __init__(self):
        self.cur = Cursor()

    def cursor(self, **kwargs):
        return self.cur


def test_sql_parameterization_vector_order_and_literal_filters():
    conn = Connection()
    attack = "x%' OR true --"
    queries.search(conn, VECTOR, visibility=("public",), limit=3,
                   category="Segmentation and Territory", topic=attack,
                   entities=("MEDDIC",), context={"who": "AE"})
    sql, params = conn.cur.sql, conn.cur.params
    assert "FROM served_units" in sql
    assert "embedding IS NOT NULL" in sql
    assert "ORDER BY cosine_distance, s.unit_id" in sql
    assert attack not in sql
    assert params[0] == queries.vector_literal(VECTOR)
    assert params[1] == ["public"]
    assert literal_pattern(attack) in params
    assert sql.count("%s") == len(params)
    assert params[-1] == 3


def test_source_injection_and_visibility_are_parameterized():
    conn = Connection()
    identifier = "'; DROP TABLE units; --"
    queries.sources(conn, identifier, identifier_type="doc_id", visibility=("public",), limit=2)
    assert identifier not in conn.cur.sql
    assert conn.cur.params == (identifier, ["public"], 2)
    assert "s.doc_id = %s" in conn.cur.sql
    with pytest.raises(ValueError):
        queries.sources(conn, "x", identifier_type="DROP", visibility=("public",), limit=2)


@pytest.mark.parametrize("vector", [[0.1], [float("nan")] * 384, [float("inf")] * 384, [0] * 384])
def test_invalid_vectors_rejected(vector):
    with pytest.raises(ValueError):
        queries.vector_literal(vector)


def test_comparison_requires_evidence_for_each_approach():
    with patch.object(tools, "service") as service:
        service.search.side_effect = [{"results": [{"claim": "Example"}], "status": "ok"},
                                      {"results": [], "status": "no_results"}]
        response = tools.compare_approaches(["MEDDICC", "BANT"], "Qualification")
    assert response["status"] == "insufficient_evidence"
    assert [call.kwargs["entity"] for call in service.search.call_args_list] == ["MEDDICC", "BANT"]
    with pytest.raises(ValueError):
        tools.compare_approaches(["BANT", "bant"], "Test")


def test_objection_mapping_and_audit_use_cited_results():
    from mcp_server.ranking import result
    def response(*args, **kwargs):
        return {"results": [result(unit())], "message": "Candidates", "status": "ok"}
    with patch.object(tools.service, "search", side_effect=response) as search:
        tools.get_objection_handling("Too expensive")
        assert "Objection handling" in search.call_args.args[0]
        mapping = tools.map_value_drivers("SMB", "CRM")
        assert mapping["candidate_value_drivers"][0]["reported_outcome"] is None
        assert mapping["candidate_value_drivers"][0]["applicability"] == "requires_review"
        audit = tools.audit_messaging_alignment("We identify the economic buyer.", "Qualification")
        assert "buyer" in audit["review_items"][0]["shared_terms"]
        assert audit["review_items"][0]["assessment"] == "requires_review"


def test_score_has_traceable_matches_and_discloses_limits():
    response = tools.score_adherence_metric("Find the Economic\nBuyer; not a salesforce.",
                                            ["economic buyer", "sales", "budget"])
    assert response["score"] == 33.33
    match = response["criteria"][0]
    assert match["evidence"] == "Economic\nBuyer"
    assert "negated" in response["limitations"]
    with pytest.raises(ValueError):
        tools.score_adherence_metric("test", [])
    with pytest.raises(ValueError):
        tools.score_adherence_metric("test", ["buyer", "BUYER"])


def test_real_mcp_http_lists_nine_tools_and_calls_score(monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "testserver")
    monkeypatch.setenv("MCP_ALLOWED_VISIBILITY", "public,internal")
    async def run():
        app = create_server().streamable_http_app()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://testserver") as client:
                headers = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}
                async def rpc(method, params, request_id):
                    response = await client.post("/mcp", headers=headers, json={
                        "jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
                    assert response.status_code == 200, response.text
                    return response.json()
                initialized = await rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"}}, 1)
                assert "serverInfo" in initialized["result"]
                listing = await rpc("tools/list", {}, 2)
                entries = listing["result"]["tools"]
                assert {t["name"] for t in entries} == {f.__name__ for f in tools.TOOL_FUNCTIONS}
                assert all(t["annotations"]["readOnlyHint"] for t in entries)
                called = await rpc("tools/call", {"name": "score_adherence_metric", "arguments": {
                    "content": "Ask the buyer about budget", "criteria": ["budget", "timeline"]}}, 3)
                assert not called["result"].get("isError", False)
                assert called["result"]["structuredContent"]["score"] == 50.0
                arguments = {
                    "get_sales_methodology": {"query": "Qualification"},
                    "get_segmentation_guidance": {"query": "Territory design"},
                    "get_enablement_practices": {"query": "Coaching"},
                    "get_source": {"identifier": "ku-test"},
                    "get_objection_handling": {"objection": "Too expensive"},
                    "compare_approaches": {"approaches": ["MEDDICC", "BANT"], "question": "Qualify?"},
                    "map_value_drivers": {"customer_context": "SMB", "offering": "CRM"},
                    "audit_messaging_alignment": {"message": "Identify buyer", "reference_query": "Qualification"},
                }
                service = RetrievalService(connection, lambda _: [VECTOR])
                with patch.object(tools, "service", service), patch.object(queries, "search", return_value=[unit()]), patch.object(queries, "sources", return_value=[unit()]):
                    for request_id, (name, args) in enumerate(arguments.items(), 4):
                        called = await rpc("tools/call", {"name": name, "arguments": args}, request_id)
                        assert not called["result"].get("isError", False), called
                        assert called["result"]["structuredContent"]["status"] == "ok"
                # Transport validation rejects malformed arguments before reaching retrieval.
                invalid = await rpc("tools/call", {"name": "get_source", "arguments": {}}, 20)
                assert invalid["result"]["isError"]
                rejected = await client.post("/mcp", headers={**headers, "Host": "untrusted.example"}, json={
                    "jsonrpc": "2.0", "id": 21, "method": "tools/list", "params": {}})
                assert rejected.status_code == 421
    asyncio.run(run())
