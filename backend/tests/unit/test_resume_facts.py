from app.domain.matching.resume_facts import estimate_years_experience, extract_education_text


def test_single_role_years_are_counted():
    parsed = {"experience": [{"company": "Acme", "start_date": "2018", "end_date": "2022"}]}
    assert estimate_years_experience(parsed, now_year=2026) == 4.0


def test_present_end_date_counts_to_current_year():
    parsed = {"experience": [{"company": "Acme", "start_date": "2022", "end_date": "Present"}]}
    assert estimate_years_experience(parsed, now_year=2026) == 4.0


def test_missing_end_date_treated_as_present():
    parsed = {"experience": [{"company": "Acme", "start_date": "2024"}]}
    assert estimate_years_experience(parsed, now_year=2026) == 2.0


def test_overlapping_roles_are_not_double_counted():
    # Two concurrent roles 2020-2022 = 2 years of experience, not 4.
    parsed = {
        "experience": [
            {"company": "A", "start_date": "2020", "end_date": "2022"},
            {"company": "B", "start_date": "2020", "end_date": "2022"},
        ]
    }
    assert estimate_years_experience(parsed, now_year=2026) == 2.0


def test_sequential_roles_accumulate():
    parsed = {
        "experience": [
            {"company": "A", "start_date": "2016", "end_date": "2018"},
            {"company": "B", "start_date": "2018", "end_date": "2021"},
        ]
    }
    assert estimate_years_experience(parsed, now_year=2026) == 5.0


def test_full_date_strings_are_handled():
    parsed = {"experience": [{"company": "A", "start_date": "Jan 2019", "end_date": "Dec 2023"}]}
    assert estimate_years_experience(parsed, now_year=2026) == 4.0


def test_no_parseable_dates_returns_none():
    # None means "unknown", which the scorer treats differently from zero.
    parsed = {"experience": [{"company": "A", "start_date": "a while ago"}]}
    assert estimate_years_experience(parsed, now_year=2026) is None


def test_empty_or_missing_experience_returns_none():
    assert estimate_years_experience({}, now_year=2026) is None
    assert estimate_years_experience({"experience": []}, now_year=2026) is None
    assert estimate_years_experience(None, now_year=2026) is None


def test_reversed_dates_are_tolerated():
    parsed = {"experience": [{"company": "A", "start_date": "2022", "end_date": "2018"}]}
    assert estimate_years_experience(parsed, now_year=2026) == 4.0


def test_extract_education_text_flattens_entries():
    parsed = {
        "education": [
            {"institution": "MIT", "degree": "BSc", "field_of_study": "Computer Science"},
        ]
    }
    text = extract_education_text(parsed)
    assert "BSc" in text and "Computer Science" in text and "MIT" in text


def test_extract_education_handles_missing_fields():
    parsed = {"education": [{"institution": "MIT"}]}
    assert extract_education_text(parsed) == "MIT"


def test_extract_education_returns_none_when_absent():
    assert extract_education_text({}) is None
    assert extract_education_text({"education": []}) is None
    assert extract_education_text(None) is None
