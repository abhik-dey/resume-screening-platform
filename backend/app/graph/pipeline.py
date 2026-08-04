"""
LangGraph pipeline for the resume-scoped agents.

DESIGN: this is a THIN orchestration layer. Every node calls the same agent
object the standalone endpoints call — no business logic lives here. If
LangGraph were removed, the agents would be untouched; only the sequencing
would need replacing. Orchestration frameworks are a poor place to
accumulate domain logic, since they're the thing most likely to be swapped.

FATAL vs NON-FATAL STEPS
------------------------
The central decision this graph encodes. Some steps are prerequisites and
some are enrichment:

  FATAL (halts the pipeline on failure):
    parse           - nothing downstream works without structured data
    extract_skills  - matching compares skills; without them the score is
                      meaningless rather than merely lower
    match           - feedback derives its recommendation from the score

  NON-FATAL (records the failure, continues):
    interview_questions - fewer questions is a degraded result, not a wrong one
    feedback            - useful but not a prerequisite for anything after it
    index               - search is a separate capability entirely

Continuing past a failed parse would produce a report full of empty
sections presented as though they were findings — worse than an honest
partial result.
"""
from typing import Any
from uuid import UUID

from langgraph.graph import END, START, StateGraph

from app.agents.feedback.agent import FeedbackAgent
from app.agents.interview_question.agent import InterviewQuestionAgent
from app.agents.matching.agent import MatchingAgent
from app.agents.resume_parser.agent import ResumeParsingAgent
from app.agents.skill_extractor.agent import SkillExtractionAgent
from app.graph.state import PipelineState
from app.services.indexing_service import IndexingError, IndexingService

# Steps whose failure means downstream steps would operate on missing or
# invalid data. Kept as a named constant so the policy is visible in one
# place rather than scattered through conditional edges.
FATAL_STEPS = frozenset({"parse", "extract_skills", "match"})


def _record(step: str, success: bool, reasoning: str, extra: dict | None = None) -> dict[str, Any]:
    """Build the partial state update a node returns."""
    detail = {"success": success, "reasoning": reasoning}
    if extra:
        detail.update(extra)

    update: dict[str, Any] = {"step_details": {step: detail}}
    if success:
        update["completed_steps"] = [step]
    else:
        update["failed_steps"] = [step]
        if step in FATAL_STEPS:
            update["halted"] = True
            update["halt_reason"] = f"Pipeline halted: required step '{step}' failed. {reasoning}"
    return update


def _skip(step: str) -> dict[str, Any]:
    """A no-op update for nodes reached after a halt.

    LangGraph edges are resolved before a node runs, so a node can still be
    entered after an upstream halt. Checking the flag inside each node makes
    the short-circuit reliable regardless of edge evaluation order.
    """
    return {
        "step_details": {step: {"success": False, "reasoning": "Skipped: pipeline halted earlier."}}
    }


def build_pipeline(
    parsing_agent: ResumeParsingAgent,
    skill_agent: SkillExtractionAgent,
    matching_agent: MatchingAgent,
    question_agent: InterviewQuestionAgent,
    feedback_agent: FeedbackAgent,
    indexing_service: IndexingService,
):
    """Construct the compiled resume pipeline graph.

    Agents are injected rather than constructed here, so the graph is
    testable with fakes and holds no knowledge of how agents are wired.
    """

    async def parse_node(state: PipelineState) -> dict[str, Any]:
        result = await parsing_agent.parse(state["resume_id"])
        return _record("parse", result.success, result.reasoning)

    async def skills_node(state: PipelineState) -> dict[str, Any]:
        if state.get("halted"):
            return _skip("extract_skills")
        result = await skill_agent.extract(state["resume_id"])
        return _record("extract_skills", result.success, result.reasoning)

    async def match_node(state: PipelineState) -> dict[str, Any]:
        if state.get("halted"):
            return _skip("match")
        result = await matching_agent.match(state["resume_id"])
        extra = {}
        if result.output and "breakdown" in result.output:
            extra["similarity_score"] = result.output["breakdown"].get("overall_score")
        return _record("match", result.success, result.reasoning, extra)

    async def questions_node(state: PipelineState) -> dict[str, Any]:
        if state.get("halted"):
            return _skip("interview_questions")
        result = await question_agent.generate(state["resume_id"])
        extra = {}
        if result.output:
            extra["question_count"] = len(result.output.get("questions", []))
        return _record("interview_questions", result.success, result.reasoning, extra)

    async def feedback_node(state: PipelineState) -> dict[str, Any]:
        if state.get("halted"):
            return _skip("feedback")
        result = await feedback_agent.generate(state["resume_id"])
        extra = {}
        if result.output:
            extra["recommendation"] = result.output.get("recommendation")
        return _record("feedback", result.success, result.reasoning, extra)

    async def index_node(state: PipelineState) -> dict[str, Any]:
        if state.get("halted"):
            return _skip("index")
        try:
            output = await indexing_service.index_resume(state["resume_id"])
        except IndexingError as exc:
            return _record("index", False, str(exc))
        except Exception as exc:  # noqa: BLE001 -- indexing failure must not abort the run
            # Broader than IndexingError deliberately: a misconfigured or
            # unreachable embedding provider raises provider-specific
            # exceptions, and search being unavailable shouldn't discard
            # a resume's completed parse, score, and feedback.
            return _record("index", False, f"{type(exc).__name__}: {exc}")
        return _record(
            "index",
            True,
            f"Indexed for semantic search ({output['dimensions']} dimensions).",
            {"embedding_model": output.get("embedding_model")},
        )

    def route_after_fatal_step(state: PipelineState) -> str:
        return "halt" if state.get("halted") else "continue"

    graph = StateGraph(PipelineState)
    graph.add_node("parse", parse_node)
    graph.add_node("extract_skills", skills_node)
    graph.add_node("match", match_node)
    graph.add_node("interview_questions", questions_node)
    graph.add_node("feedback", feedback_node)
    graph.add_node("index", index_node)

    graph.add_edge(START, "parse")

    # Conditional edges after each fatal step: a failure routes straight to
    # END rather than walking through the remaining nodes.
    for step, next_step in (
        ("parse", "extract_skills"),
        ("extract_skills", "match"),
        ("match", "interview_questions"),
    ):
        graph.add_conditional_edges(
            step, route_after_fatal_step, {"continue": next_step, "halt": END}
        )

    # Non-fatal steps run unconditionally; each checks the halt flag itself.
    graph.add_edge("interview_questions", "feedback")
    graph.add_edge("feedback", "index")
    graph.add_edge("index", END)

    return graph.compile()


def describe_pipeline() -> dict[str, Any]:
    """Machine-readable description of the pipeline structure.

    Exposed via the API so the sequence and its failure policy are
    discoverable rather than something a caller has to infer.
    """
    return {
        "steps": [
            {"name": "parse", "fatal": True, "description": "Extract structured data from the resume file"},
            {"name": "extract_skills", "fatal": True, "description": "Normalize and categorize skills"},
            {"name": "match", "fatal": True, "description": "Compute the deterministic match score"},
            {"name": "interview_questions", "fatal": False, "description": "Generate tailored questions"},
            {"name": "feedback", "fatal": False, "description": "Derive recommendation and narrative"},
            {"name": "index", "fatal": False, "description": "Embed for semantic search"},
        ],
        "fatal_step_policy": (
            "Failure of a fatal step halts the pipeline, because downstream steps would "
            "operate on missing or invalid data. Non-fatal failures are recorded and the "
            "pipeline continues."
        ),
    }


async def run_resume_pipeline(pipeline, resume_id: UUID, job_id: UUID | None = None) -> PipelineState:
    """Execute the compiled pipeline for one resume."""
    from app.graph.state import initial_state

    return await pipeline.ainvoke(initial_state(resume_id, job_id))
