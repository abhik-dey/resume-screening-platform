"""
LangGraph pipeline tests using stub agents.

The fatal/non-fatal distinction gets the most attention: continuing past a
failed parse would produce a report full of empty sections presented as
findings, which is worse than an honest partial result.
"""
import uuid
from dataclasses import dataclass

from app.graph.pipeline import FATAL_STEPS, build_pipeline, describe_pipeline, run_resume_pipeline
from app.services.indexing_service import IndexingError


@dataclass
class StubResult:
    success: bool
    reasoning: str
    output: dict | None = None


class StubAgent:
    """Records that it ran, and returns a scripted result."""

    def __init__(self, success: bool = True, output: dict | None = None) -> None:
        self._success = success
        self._output = output
        self.call_count = 0

    def _result(self) -> StubResult:
        self.call_count += 1
        return StubResult(
            success=self._success,
            reasoning="ok" if self._success else "deliberate failure",
            output=self._output,
        )

    async def parse(self, resume_id):
        return self._result()

    async def extract(self, resume_id):
        return self._result()

    async def match(self, resume_id):
        return self._result()

    async def generate(self, resume_id):
        return self._result()


class StubIndexing:
    def __init__(self, should_fail: bool = False, raise_unexpected: bool = False) -> None:
        self._should_fail = should_fail
        self._raise_unexpected = raise_unexpected
        self.call_count = 0

    async def index_resume(self, resume_id):
        self.call_count += 1
        if self._raise_unexpected:
            raise RuntimeError("embedding provider unreachable")
        if self._should_fail:
            raise IndexingError("deliberate indexing failure")
        return {"dimensions": 128, "embedding_model": "stub"}


def _build(**overrides):
    agents = {
        "parsing_agent": StubAgent(),
        "skill_agent": StubAgent(),
        "matching_agent": StubAgent(output={"breakdown": {"overall_score": 0.85}}),
        "question_agent": StubAgent(output={"questions": [1, 2, 3]}),
        "feedback_agent": StubAgent(output={"recommendation": "recommend"}),
        "indexing_service": StubIndexing(),
    }
    agents.update(overrides)
    return build_pipeline(**agents), agents


async def test_happy_path_runs_every_step_in_order():
    pipeline, agents = _build()
    state = await run_resume_pipeline(pipeline, uuid.uuid4())

    assert state["completed_steps"] == [
        "parse", "extract_skills", "match", "interview_questions", "feedback", "index",
    ]
    assert state["failed_steps"] == []
    assert state["halted"] is False


async def test_parse_failure_halts_everything_downstream():
    skill_agent = StubAgent()
    matching_agent = StubAgent()
    pipeline, _ = _build(
        parsing_agent=StubAgent(success=False),
        skill_agent=skill_agent,
        matching_agent=matching_agent,
    )
    state = await run_resume_pipeline(pipeline, uuid.uuid4())

    assert state["halted"] is True
    assert "parse" in state["failed_steps"]
    assert state["completed_steps"] == []
    # Downstream agents must never be invoked — running them against a
    # resume with no parsed data wastes API calls and produces noise.
    assert skill_agent.call_count == 0
    assert matching_agent.call_count == 0


async def test_skill_extraction_failure_halts_the_pipeline():
    matching_agent = StubAgent()
    pipeline, _ = _build(skill_agent=StubAgent(success=False), matching_agent=matching_agent)
    state = await run_resume_pipeline(pipeline, uuid.uuid4())

    assert state["halted"] is True
    assert state["completed_steps"] == ["parse"]
    assert matching_agent.call_count == 0


async def test_match_failure_halts_the_pipeline():
    question_agent = StubAgent()
    pipeline, _ = _build(matching_agent=StubAgent(success=False), question_agent=question_agent)
    state = await run_resume_pipeline(pipeline, uuid.uuid4())

    assert state["halted"] is True
    assert state["completed_steps"] == ["parse", "extract_skills"]
    assert question_agent.call_count == 0


async def test_question_failure_does_not_halt_the_pipeline():
    # Fewer interview questions is a degraded result, not a wrong one —
    # the feedback and index steps still produce genuine value.
    feedback_agent = StubAgent()
    pipeline, _ = _build(question_agent=StubAgent(success=False), feedback_agent=feedback_agent)
    state = await run_resume_pipeline(pipeline, uuid.uuid4())

    assert state["halted"] is False
    assert "interview_questions" in state["failed_steps"]
    assert "feedback" in state["completed_steps"]
    assert "index" in state["completed_steps"]
    assert feedback_agent.call_count == 1


async def test_feedback_failure_does_not_halt_the_pipeline():
    pipeline, _ = _build(feedback_agent=StubAgent(success=False))
    state = await run_resume_pipeline(pipeline, uuid.uuid4())

    assert state["halted"] is False
    assert "feedback" in state["failed_steps"]
    assert "index" in state["completed_steps"]


async def test_indexing_failure_does_not_halt_the_pipeline():
    pipeline, _ = _build(indexing_service=StubIndexing(should_fail=True))
    state = await run_resume_pipeline(pipeline, uuid.uuid4())

    assert state["halted"] is False
    assert "index" in state["failed_steps"]
    # Everything of substance still completed.
    assert "feedback" in state["completed_steps"]


async def test_unexpected_indexing_exception_is_caught():
    # A misconfigured embedding provider raises provider-specific errors,
    # not IndexingError. Losing a resume's completed parse/score/feedback
    # because search is unavailable would be the wrong trade.
    pipeline, _ = _build(indexing_service=StubIndexing(raise_unexpected=True))
    state = await run_resume_pipeline(pipeline, uuid.uuid4())

    assert state["halted"] is False
    assert "index" in state["failed_steps"]
    assert "RuntimeError" in state["step_details"]["index"]["reasoning"]


async def test_step_details_capture_agent_output():
    pipeline, _ = _build()
    state = await run_resume_pipeline(pipeline, uuid.uuid4())

    assert state["step_details"]["match"]["similarity_score"] == 0.85
    assert state["step_details"]["interview_questions"]["question_count"] == 3
    assert state["step_details"]["feedback"]["recommendation"] == "recommend"


async def test_halt_reason_names_the_failing_step():
    pipeline, _ = _build(matching_agent=StubAgent(success=False))
    state = await run_resume_pipeline(pipeline, uuid.uuid4())

    assert "match" in state["halt_reason"]
    assert "halted" in state["halt_reason"].lower()


async def test_each_agent_runs_exactly_once():
    pipeline, agents = _build()
    await run_resume_pipeline(pipeline, uuid.uuid4())

    for name in ("parsing_agent", "skill_agent", "matching_agent", "question_agent", "feedback_agent"):
        assert agents[name].call_count == 1, f"{name} ran {agents[name].call_count} times"
    assert agents["indexing_service"].call_count == 1


async def test_job_id_is_carried_through_state():
    pipeline, _ = _build()
    job_id = uuid.uuid4()
    state = await run_resume_pipeline(pipeline, uuid.uuid4(), job_id)
    assert state["job_id"] == job_id


def test_fatal_steps_are_the_prerequisites():
    assert FATAL_STEPS == {"parse", "extract_skills", "match"}


def test_describe_pipeline_matches_actual_execution_order():
    described = [s["name"] for s in describe_pipeline()["steps"]]
    assert described == [
        "parse", "extract_skills", "match", "interview_questions", "feedback", "index",
    ]
    fatal_in_description = {s["name"] for s in describe_pipeline()["steps"] if s["fatal"]}
    # The published description must not drift from the enforced policy.
    assert fatal_in_description == FATAL_STEPS
