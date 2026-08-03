from app.domain.entities.skill import SkillCategory
from app.domain.skills.normalizer import resolve_from_dictionary


def test_spec_example_cpp_variants_all_resolve_identically():
    # The exact example from the original spec: "C++", "C Plus Plus", and
    # "C plus plus" must all normalize to the same canonical skill.
    for variant in ["C++", "C Plus Plus", "c plus plus", "cpp", "C ++"]:
        result = resolve_from_dictionary(variant)
        assert result is not None, f"expected a match for {variant!r}"
        assert result.canonical_name == "C++"
        assert result.category == SkillCategory.PROGRAMMING


def test_case_and_whitespace_insensitivity():
    result_a = resolve_from_dictionary("PYTHON")
    result_b = resolve_from_dictionary("  python  ")
    result_c = resolve_from_dictionary("Python")
    assert result_a.canonical_name == result_b.canonical_name == result_c.canonical_name == "Python"


def test_dictionary_confidence_is_full():
    result = resolve_from_dictionary("python")
    assert result.confidence == 1.0


def test_one_skill_from_each_category_resolves_correctly():
    cases = [
        ("java", "Java", SkillCategory.PROGRAMMING),
        ("k8s", "Kubernetes", SkillCategory.CLOUD),
        ("postgres", "PostgreSQL", SkillCategory.DATABASES),
        ("ml", "Machine Learning", SkillCategory.AI),
        ("ci/cd", "CI/CD", SkillCategory.DEVOPS),
        ("leadership", "Leadership", SkillCategory.SOFT_SKILLS),
    ]
    for raw, expected_name, expected_category in cases:
        result = resolve_from_dictionary(raw)
        assert result is not None, f"expected a match for {raw!r}"
        assert result.canonical_name == expected_name
        assert result.category == expected_category


def test_spacing_variants_around_symbols_resolve():
    # Real resumes contain spacing inconsistencies like these.
    assert resolve_from_dictionary("C ++").canonical_name == "C++"
    assert resolve_from_dictionary("CI / CD").canonical_name == "CI/CD"
    assert resolve_from_dictionary("C #").canonical_name == "C#"


def test_word_based_aliases_still_require_their_spaces():
    # The symbol-stripping fallback must not break multi-word aliases:
    # "c plus plus" has no symbols, so it matches via its own alias, and
    # "machine learning" must not collapse into "machinelearning".
    assert resolve_from_dictionary("c plus plus").canonical_name == "C++"
    assert resolve_from_dictionary("machine learning").canonical_name == "Machine Learning"


def test_unknown_skill_returns_none():
    result = resolve_from_dictionary("some obscure proprietary internal tool xyz123")
    assert result is None


def test_raw_field_preserves_original_input():
    result = resolve_from_dictionary("  PostgreSQL  ")
    assert result.raw == "  PostgreSQL  "
    assert result.canonical_name == "PostgreSQL"
