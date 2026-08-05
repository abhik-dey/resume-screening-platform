"""
Output guard tests.

These check that fairness constraints are verified rather than merely
requested — the gap flagged in Phases 11 and 12.
"""
from app.domain.security.output_guard import scan_output


def test_age_related_questions_are_flagged():
    result = scan_output(["How old are you?", "What year did you graduate?"])
    assert result.flagged is True
    assert "age" in result.categories


def test_family_status_questions_are_flagged():
    result = scan_output(["Do you have children?", "Are you married?"])
    assert "family_status" in result.categories


def test_nationality_questions_are_flagged():
    result = scan_output(["What is your visa status?", "Where are you from originally?"])
    assert "nationality" in result.categories


def test_disability_questions_are_flagged():
    result = scan_output(["Do you have any medical conditions we should know about?"])
    assert "disability" in result.categories


def test_religion_questions_are_flagged():
    result = scan_output(["Do you observe any religious holidays?"])
    assert "religion" in result.categories


def test_employment_gap_speculation_is_flagged():
    # Explicitly forbidden in the Phase 12 feedback prompt; now verified.
    result = scan_output(["There is a gap in your employment history — why?"])
    assert "employment_gap_speculation" in result.categories


def test_legitimate_technical_questions_are_not_flagged():
    result = scan_output([
        "Walk me through how you'd containerize the payment service you built.",
        "Describe a technical disagreement you navigated with a colleague.",
        "What was the hardest bug in your Kubernetes migration?",
        "How do you approach database schema design?",
    ])
    assert result.flagged is False


def test_flagged_items_identify_which_item_and_why():
    result = scan_output([
        "What is your greatest technical strength?",
        "How old are you?",
    ])
    assert len(result.flagged_items) == 1
    assert result.flagged_items[0]["index"] == 1
    assert "age" in result.flagged_items[0]["categories"]


def test_summary_explains_the_liability():
    result = scan_output(["Are you planning to have children?"])
    assert "discrimination" in result.summary.lower()


def test_empty_input_is_safe():
    assert scan_output([]).flagged is False
    assert scan_output(["", None or ""]).flagged is False


def test_flagged_text_is_truncated_in_the_report():
    result = scan_output(["How old are you? " + "x" * 500])
    assert len(result.flagged_items[0]["text"]) <= 200
