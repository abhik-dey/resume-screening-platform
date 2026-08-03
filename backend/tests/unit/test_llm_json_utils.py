from pydantic import BaseModel

from app.agents.llm_json_utils import call_llm_for_json, strip_markdown_fences
from app.domain.interfaces.llm_provider import LLMProvider


class _Sample(BaseModel):
    value: int


class _ScriptedLLM(LLMProvider):
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.call_count = 0

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.call_count += 1
        return self._responses.pop(0)


def test_strip_markdown_fences_removes_json_fence():
    fenced = '```json\n{"value": 1}\n```'
    assert strip_markdown_fences(fenced) == '{"value": 1}'


def test_strip_markdown_fences_leaves_plain_json_untouched():
    plain = '{"value": 1}'
    assert strip_markdown_fences(plain) == plain


async def test_call_llm_for_json_succeeds_first_attempt():
    llm = _ScriptedLLM(['{"value": 42}'])
    result = await call_llm_for_json(
        llm=llm,
        system_prompt="sys",
        user_prompt="user",
        validate=_Sample.model_validate,
        build_retry_prompt=lambda prev: "retry",
    )
    assert result.value == 42
    assert llm.call_count == 1


async def test_call_llm_for_json_retries_once_on_malformed_response():
    llm = _ScriptedLLM(["not json", '{"value": 7}'])
    result = await call_llm_for_json(
        llm=llm,
        system_prompt="sys",
        user_prompt="user",
        validate=_Sample.model_validate,
        build_retry_prompt=lambda prev: "retry",
    )
    assert result.value == 7
    assert llm.call_count == 2


async def test_call_llm_for_json_returns_none_after_exhausting_attempts():
    llm = _ScriptedLLM(["garbage", "still garbage"])
    result = await call_llm_for_json(
        llm=llm,
        system_prompt="sys",
        user_prompt="user",
        validate=_Sample.model_validate,
        build_retry_prompt=lambda prev: "retry",
        max_attempts=2,
    )
    assert result is None
    assert llm.call_count == 2


async def test_call_llm_for_json_handles_markdown_fenced_response():
    llm = _ScriptedLLM(['```json\n{"value": 5}\n```'])
    result = await call_llm_for_json(
        llm=llm,
        system_prompt="sys",
        user_prompt="user",
        validate=_Sample.model_validate,
        build_retry_prompt=lambda prev: "retry",
    )
    assert result.value == 5
