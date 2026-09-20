"""Local HTTP protocol tests; never reported as a real external LLM evaluation."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from coastmas.core.errors import CoastMASError
from coastmas.core.llm import OpenAICompatibleProvider, PlanningPrompt, ProviderSettings
from coastmas.persistence.planning import create_trace
from coastmas.persistence.resources import fingerprint
from coastmas.persistence.schema import ProviderRequest


@pytest.fixture
def server():
    requests = []
    response = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": json.dumps(
                        {
                            "management_goal": "protocol test only",
                            "task_graph": [],
                            "required_data": [],
                            "required_capabilities": [],
                            "candidate_workflow": None,
                            "missing_conditions": ["No models supplied in this protocol fixture"],
                            "rationale": ["local test response"],
                        }
                    )
                },
            }
        ],
        "usage": {
            "prompt_tokens": 101,
            "completion_tokens": 31,
            "total_tokens": 132,
            "prompt_tokens_details": {"cached_tokens": 20},
        },
    }

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            requests.append(json.loads(self.rfile.read(length)))
            raw = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):
            pass

    service = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{service.server_port}/v1", requests, response
    service.shutdown()
    service.server_close()
    thread.join()


def setup(engine, actors, server):
    url, _, _ = server
    prompt = PlanningPrompt(
        goal="protocol test only",
        scene_summary={"id": "s", "version": 1},
        models=(),
        data=(),
        candidate_total=0,
    )
    with Session(engine) as session, session.begin():
        trace = create_trace(
            session,
            actors[0],
            actors[3],
            key=str(uuid4()),
            allow_external=True,
            inputs={"allowed_prompt_fingerprints": [fingerprint(prompt.model_dump(mode="json"))]},
        )
        trace_id = trace.id
    provider = OpenAICompatibleProvider(
        ProviderSettings(
            base_url=url,
            model="local-protocol-fixture",
            api_key="local-fixture-only",
            allow_private=True,
        )
    )
    return provider, prompt, trace_id


def test_actual_http_requests_share_budget_and_usage_is_provider_reported(engine, actors, server):
    provider, prompt, identifier = setup(engine, actors, server)
    for _ in range(2):
        result = provider.generate(engine, actors[0], identifier, prompt)
        assert result.proposal.missing_conditions
        assert result.usage["input_tokens"] == 101
        assert result.usage["cached_input_tokens"] == 20
    with pytest.raises(CoastMASError, match="budget"):
        provider.generate(engine, actors[0], identifier, prompt)
    assert len(server[1]) == 2
    request = server[1][0]
    assert request["response_format"]["json_schema"]["strict"] is True
    assert request["max_completion_tokens"] > 0
    assert "local-fixture-only" not in json.dumps(request)
    with Session(engine) as session:
        records = list(
            session.scalars(select(ProviderRequest).where(ProviderRequest.trace_id == identifier))
        )
        assert [item.status for item in records] == ["SUCCEEDED", "SUCCEEDED"]
        assert all(item.dispatched_at and item.finished_at for item in records)
        assert all(item.provider_model == "local-protocol-fixture" for item in records)
        assert all(item.http_status == 200 for item in records)


@pytest.mark.parametrize("kind", ["length", "refusal", "malformed", "unknown_field"])
def test_invalid_or_truncated_response_is_not_repaired_or_retried_implicitly(
    engine, actors, server, kind
):
    provider, prompt, identifier = setup(engine, actors, server)
    choice = server[2]["choices"][0]
    if kind == "length":
        choice["finish_reason"] = "length"
    elif kind == "refusal":
        choice["message"]["refusal"] = "fixture refusal"
    elif kind == "malformed":
        choice["message"]["content"] = "{"
    else:
        content = json.loads(choice["message"]["content"])
        content["execute_code"] = "forbidden"
        choice["message"]["content"] = json.dumps(content)
    with pytest.raises(CoastMASError):
        provider.generate(engine, actors[0], identifier, prompt)
    assert len(server[1]) == 1
    with Session(engine) as session:
        item = session.scalar(select(ProviderRequest).where(ProviderRequest.trace_id == identifier))
        assert item.status == "INVALID"
        assert item.usage["input_tokens"] == 101


def test_prompt_must_match_authorized_trace_and_unknown_usage_is_null(engine, actors, server):
    provider, prompt, identifier = setup(engine, actors, server)
    with pytest.raises(CoastMASError):
        provider.generate(
            engine, actors[0], identifier, prompt.model_copy(update={"goal": "new data"})
        )
    assert not server[1]
    del server[2]["usage"]
    result = provider.generate(engine, actors[0], identifier, prompt)
    assert result.usage is None
