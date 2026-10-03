import logging
from collections.abc import Callable
from types import SimpleNamespace

import httpx
import pytest
from app.agents.itinerary.engine import estimate_cost_usd
from app.agents.itinerary.structured_output import (
    OpenAIStructuredOutput,
    StructuredCompletion,
    StructuredOutputFailed,
    StructuredOutputPort,
    StructuredOutputTimeout,
    StructuredUsage,
)
from app.core.config import Settings
from app.core.exceptions import LLMTimeoutError
from openai import APIConnectionError, APITimeoutError
from pydantic import BaseModel


class Choice(BaseModel):
    selected_id: str


SYSTEM = "SYSTEM-SENTINEL"
USER = "USER-SENTINEL"


class FakeStructuredOutput:
    def __init__(self, parsed: object) -> None:
        self.parsed = parsed
        self.roles: list[str] = []

    async def complete(
        self,
        *,
        role: str,
        system: str,
        user: str,
        schema: type[BaseModel],
        deterministic: Callable[[], object],
    ) -> StructuredCompletion:
        del system, user, schema, deterministic
        self.roles.append(role)
        return StructuredCompletion(
            parsed=self.parsed,
            usage=StructuredUsage(
                model="fake",
                input_tokens=0,
                output_tokens=0,
                estimated_cost_usd=0.0,
                retry_count=0,
                attempts=0,
                prompt_sent=False,
                safe_metadata={},
            ),
        )


def _refuse() -> object:
    raise AssertionError("deterministic path used")


async def _ask(port: StructuredOutputPort, *, role: str = "research") -> StructuredCompletion:
    return await port.complete(
        role=role,
        system=SYSTEM,
        user=USER,
        schema=Choice,
        deterministic=_refuse,
    )


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "openai_api_key": "",
        "openai_model": "gpt-4o-mini",
        "planner_model": "planner-model-must-not-be-read",
        "openai_timeout_seconds": 19,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _usage(input_tokens: int, output_tokens: int) -> SimpleNamespace:
    return SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)


def _parsed(selected: str, usage: object) -> SimpleNamespace:
    return SimpleNamespace(
        output_parsed=Choice(selected_id=selected),
        usage=usage,
        model="ignored-snapshot",
    )


def _empty(usage: object) -> SimpleNamespace:
    return SimpleNamespace(output_parsed=None, usage=usage, model="ignored-snapshot")


def _timeout() -> APITimeoutError:
    return APITimeoutError(httpx.Request("POST", "https://api.openai.com/v1/responses"))


def _connection() -> APIConnectionError:
    return APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1/responses"))


def _patch_client(
    monkeypatch: pytest.MonkeyPatch,
    script: list[object],
) -> tuple[list[dict], list[dict]]:
    created: list[dict] = []
    calls: list[dict] = []

    class Responses:
        async def parse(self, **kwargs: object) -> object:
            calls.append(kwargs)
            outcome = script[len(calls) - 1]
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

    class Client:
        def __init__(self, **kwargs: object) -> None:
            created.append(kwargs)
            self.responses = Responses()

    monkeypatch.setattr("app.agents.itinerary.structured_output.AsyncOpenAI", Client)
    return created, calls


def _spy_model_for(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    roles: list[str] = []
    original = Settings.model_for

    def spy(self: Settings, role: str) -> str:
        roles.append(role)
        return original(self, role)

    monkeypatch.setattr(Settings, "model_for", spy)
    return roles


async def test_fake_satisfies_the_port_without_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(**kwargs: object) -> None:
        del kwargs
        raise AssertionError("live client")

    monkeypatch.setattr("app.agents.itinerary.structured_output.AsyncOpenAI", explode)
    fake = FakeStructuredOutput(Choice(selected_id="kept"))

    completed = await _ask(fake, role="critic")

    assert completed.parsed == Choice(selected_id="kept")
    assert fake.roles == ["critic"]
    assert completed.usage.prompt_sent is False


@pytest.mark.parametrize("api_key", ["", "   ", "\n"])
async def test_empty_key_is_deterministic_and_does_not_construct_a_client(
    monkeypatch: pytest.MonkeyPatch,
    api_key: str,
) -> None:
    def explode(**kwargs: object) -> None:
        del kwargs
        raise AssertionError("live client")

    monkeypatch.setattr("app.agents.itinerary.structured_output.AsyncOpenAI", explode)
    settings = _settings(openai_api_key=api_key)
    roles = _spy_model_for(monkeypatch)
    calls = {"deterministic": 0}

    def deterministic() -> dict[str, str]:
        calls["deterministic"] += 1
        return {"source": "code"}

    port = OpenAIStructuredOutput(settings)
    result = await port.complete(
        role="supervisor",
        system=SYSTEM,
        user=USER,
        schema=Choice,
        deterministic=deterministic,
    )

    assert calls["deterministic"] == 1
    assert result.parsed == {"source": "code"}
    assert roles == []
    assert result.usage == StructuredUsage(
        model="deterministic",
        input_tokens=0,
        output_tokens=0,
        estimated_cost_usd=0.0,
        retry_count=0,
        attempts=0,
        prompt_sent=False,
        safe_metadata={},
    )
    assert not hasattr(result.usage, "prompt_version")
    blob = f"{result.parsed} {result.usage}"
    assert SYSTEM not in blob
    assert USER not in blob


async def test_parse_request_uses_the_role_model_and_client_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created, calls = _patch_client(monkeypatch, [_parsed("a", _usage(4, 6))])
    settings = _settings(
        openai_api_key="test-key",
        supervisor_model="supervisor-override",
    )
    roles = _spy_model_for(monkeypatch)

    port = OpenAIStructuredOutput(settings)
    result = await port.complete(
        role="supervisor",
        system=SYSTEM,
        user=USER,
        schema=Choice,
        deterministic=_refuse,
    )

    assert roles == ["supervisor"]
    assert created == [
        {
            "api_key": "test-key",
            "timeout": settings.openai_timeout_seconds,
            "max_retries": 0,
        }
    ]
    assert calls == [
        {
            "model": "supervisor-override",
            "instructions": SYSTEM,
            "input": USER,
            "text_format": Choice,
            "store": False,
        }
    ]
    assert isinstance(result.parsed, Choice)
    assert result.parsed.selected_id == "a"
    assert result.usage.model == "supervisor-override"
    assert result.usage.input_tokens == 4
    assert result.usage.output_tokens == 6
    assert result.usage.estimated_cost_usd == 0.0
    assert result.usage.safe_metadata == {"cost_unpriced": True}
    assert result.usage.prompt_sent is True
    assert result.usage.attempts == 1
    assert result.usage.retry_count == 0
    assert not hasattr(result.usage, "prompt_version")
    assert "planner-model-must-not-be-read" not in str(calls)


async def test_usage_pricing_and_missing_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    script = [
        _parsed("priced", _usage(11, 7)),
        _parsed("zeros", _usage(0, 0)),
        _parsed("missing", None),
        _parsed("other-missing", None),
    ]
    _patch_client(monkeypatch, script)
    settings = _settings(openai_api_key="test-key", research_model="other-model")
    roles = _spy_model_for(monkeypatch)
    port = OpenAIStructuredOutput(settings)

    priced = await _ask(port, role="critic")
    zeros = await _ask(port, role="critic")
    missing = await _ask(port, role="critic")
    unpriced_missing = await _ask(port, role="research")

    assert roles == ["critic", "critic", "critic", "research"]
    assert priced.usage.model == "gpt-4o-mini"
    assert priced.usage.input_tokens == 11
    assert priced.usage.output_tokens == 7
    assert priced.usage.estimated_cost_usd == estimate_cost_usd(11, 7)
    assert priced.usage.safe_metadata == {}
    assert zeros.usage.input_tokens == 0
    assert zeros.usage.output_tokens == 0
    assert zeros.usage.safe_metadata == {}
    assert missing.usage.input_tokens == 0
    assert missing.usage.output_tokens == 0
    assert missing.usage.estimated_cost_usd == 0.0
    assert missing.usage.safe_metadata == {"tokens_unreported": True}
    assert unpriced_missing.usage.model == "other-model"
    assert unpriced_missing.usage.input_tokens == 0
    assert unpriced_missing.usage.output_tokens == 0
    assert unpriced_missing.usage.safe_metadata == {
        "tokens_unreported": True,
        "cost_unpriced": True,
    }


async def test_invalid_output_retries_then_returns_on_the_third_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = [
        _empty(_usage(99, 98)),
        SimpleNamespace(output_parsed={}, usage=_usage(97, 96), model="ignored-snapshot"),
        _parsed("ok", _usage(3, 5)),
    ]
    _, calls = _patch_client(monkeypatch, script)
    port = OpenAIStructuredOutput(_settings(openai_api_key="test-key"))

    result = await _ask(port, role="critic")

    assert [call["instructions"] for call in calls] == [SYSTEM, SYSTEM, SYSTEM]
    assert calls[0]["input"] == USER
    retried = f"{USER}\n\nThe previous output was invalid: Structured output was empty."
    assert calls[1]["input"] == retried
    assert calls[2]["input"].startswith(f"{USER}\n\nThe previous output was invalid:")
    assert "Field required" in calls[2]["input"]
    assert calls[2]["model"] == "gpt-4o-mini"
    assert all(call["store"] is False for call in calls)
    assert all(call["text_format"] is Choice for call in calls)
    assert isinstance(result.parsed, Choice)
    assert result.parsed.selected_id == "ok"
    assert result.usage.input_tokens == 3
    assert result.usage.output_tokens == 5
    assert result.usage.attempts == 3
    assert result.usage.retry_count == 2
    assert result.usage.model == "gpt-4o-mini"


async def test_invalid_output_fails_closed_after_three_attempts(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    script = [
        _empty(_usage(99, 98)),
        _empty(_usage(97, 96)),
        _empty(_usage(8, 2)),
    ]
    _, calls = _patch_client(monkeypatch, script)
    port = OpenAIStructuredOutput(_settings(openai_api_key="test-key"))
    caplog.set_level(logging.INFO, logger="app.agents.itinerary.structured_output")

    with pytest.raises(StructuredOutputFailed) as caught:
        await _ask(port, role="research")

    assert len(calls) == 3
    assert caught.value.attempts == 3
    assert caught.value.retry_count == 2
    assert caught.value.code == "structured_output_invalid"
    assert caught.value.usage is not None
    assert caught.value.usage.input_tokens == 8
    assert caught.value.usage.output_tokens == 2
    assert caught.value.usage.attempts == 3
    assert caught.value.usage.prompt_sent is True
    assert "input_tokens" not in vars(caught.value)
    assert USER not in str(caught.value)
    assert SYSTEM not in caplog.text
    assert USER not in caplog.text
    assert caplog.text.count("structured_output_retry") == 3


async def test_timeout_raises_on_the_third_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    _, calls = _patch_client(monkeypatch, [_timeout(), _timeout(), _timeout()])
    port = OpenAIStructuredOutput(_settings(openai_api_key="test-key"))

    with pytest.raises(StructuredOutputTimeout) as caught:
        await _ask(port, role="supervisor")

    assert len(calls) == 3
    assert [call["input"] for call in calls] == [USER, USER, USER]
    assert isinstance(caught.value, LLMTimeoutError)
    assert caught.value.attempts == 3
    assert caught.value.retry_count == 2
    assert caught.value.usage is None
    assert caught.value.code == "openai_timeout"
    assert "input_tokens" not in vars(caught.value)


async def test_connection_error_retries_inside_the_same_three_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, calls = _patch_client(monkeypatch, [_connection(), _parsed("later", _usage(1, 1))])
    port = OpenAIStructuredOutput(_settings(openai_api_key="test-key"))

    result = await _ask(port, role="research")

    assert len(calls) == 2
    assert [call["input"] for call in calls] == [USER, USER]
    assert calls[0]["model"] == "gpt-4o-mini"
    assert isinstance(result.parsed, Choice)
    assert result.usage.attempts == 2
    assert result.usage.retry_count == 1
    assert result.usage.input_tokens == 1


async def test_timeout_keeps_the_prior_validation_error_on_the_user_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = [
        _empty(_usage(1, 1)),
        _timeout(),
        _parsed("ok", _usage(2, 2)),
    ]
    _, calls = _patch_client(monkeypatch, script)
    port = OpenAIStructuredOutput(_settings(openai_api_key="test-key"))

    result = await _ask(port, role="critic")

    note = f"{USER}\n\nThe previous output was invalid: Structured output was empty."
    assert calls[0]["input"] == USER
    assert calls[1]["input"] == note
    assert calls[2]["input"] == note
    assert result.usage.retry_count == 2
    assert result.usage.input_tokens == 2


async def test_unexpected_errors_are_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    _, calls = _patch_client(monkeypatch, [RuntimeError("boom")])
    port = OpenAIStructuredOutput(_settings(openai_api_key="test-key"))

    with pytest.raises(RuntimeError, match="boom"):
        await _ask(port, role="critic")

    assert len(calls) == 1


async def test_each_http_attempt_reserves_a_slot_before_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.agents.itinerary.structured_output import AttemptRefused, StructuredOutputFailed

    script = [
        _empty(_usage(4, 4)),
        _empty(_usage(5, 5)),
        _parsed("later", _usage(6, 6)),
    ]
    _, calls = _patch_client(monkeypatch, script)
    port = OpenAIStructuredOutput(_settings(openai_api_key="test-key"))
    taken = {"n": 0}

    async def reserve() -> None:
        if taken["n"] >= 2:
            raise AttemptRefused()
        taken["n"] += 1

    with pytest.raises(StructuredOutputFailed) as caught:
        await port.complete(
            role="research",
            system=SYSTEM,
            user=USER,
            schema=Choice,
            deterministic=_refuse,
            reserve=reserve,
        )

    assert taken["n"] == 2
    assert len(calls) == 2
    assert caught.value.attempts == 2
    assert caught.value.usage is not None
    assert caught.value.usage.input_tokens == 5
    assert caught.value.__cause__ is None


async def test_provider_api_errors_become_a_local_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.agents.itinerary.structured_output import ModelRequestFailed
    from openai import APIStatusError

    secret = "provider-secret-text"
    response = httpx.Response(
        500,
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
    )
    _, calls = _patch_client(
        monkeypatch,
        [APIStatusError(secret, response=response, body={"error": secret})],
    )
    port = OpenAIStructuredOutput(_settings(openai_api_key="test-key"))
    caplog.set_level(logging.WARNING, logger="app.agents.itinerary.structured_output")

    with pytest.raises(ModelRequestFailed) as caught:
        await _ask(port, role="research")

    assert len(calls) == 1
    assert caught.value.code == "model_request_failed"
    assert str(caught.value) == "The model request failed."
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True
    assert secret not in caplog.text
    assert SYSTEM not in caplog.text
    assert USER not in caplog.text
    assert "role=research code=model_request_failed" in caplog.text
