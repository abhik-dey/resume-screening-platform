"""
Build the text that gets embedded for resumes and jobs.

Pure and I/O-free. What goes into the embedding text determines what
semantic search can find, so this is a real design decision rather than
plumbing:

RESUMES use skills + project descriptions + experience — the substance of
what someone has done. Raw resume text was deliberately rejected: it's full
of formatting noise, addresses, and boilerplate ("References available on
request") that dilutes the signal.

JOBS use title + description + requirements, so a job's vector sits in the
same conceptual space as the resumes being matched against it.

Names, emails, and phone numbers are EXCLUDED from resume text. They add no
signal about capability, and embedding personal identifiers invites
matching on the wrong things entirely.
"""
from app.domain.entities.job import Job
from app.domain.entities.resume import Resume

MAX_EMBEDDING_CHARS = 8000


def build_resume_text(resume: Resume, skill_names: list[str]) -> str:
    parsed = resume.parsed_data or {}
    parts: list[str] = []

    if skill_names:
        parts.append("Skills: " + ", ".join(skill_names))

    for experience in parsed.get("experience") or []:
        if not isinstance(experience, dict):
            continue
        segment = " ".join(
            str(experience.get(key, "")) for key in ("title", "company", "description")
        ).strip()
        if segment:
            parts.append(f"Experience: {segment}")

    for project in parsed.get("projects") or []:
        if not isinstance(project, dict):
            continue
        technologies = ", ".join(project.get("technologies") or [])
        segment = " ".join(
            filter(None, [str(project.get("name", "")), str(project.get("description", "")), technologies])
        ).strip()
        if segment:
            parts.append(f"Project: {segment}")

    for education in parsed.get("education") or []:
        if not isinstance(education, dict):
            continue
        segment = " ".join(
            str(education.get(key, "")) for key in ("degree", "field_of_study", "institution")
        ).strip()
        if segment:
            parts.append(f"Education: {segment}")

    return _truncate("\n".join(parts))


def build_job_text(job: Job) -> str:
    parts = [f"Job title: {job.title}", f"Description: {job.description}"]
    if job.required_skills:
        parts.append("Required skills: " + ", ".join(job.required_skills))
    if job.preferred_skills:
        parts.append("Preferred skills: " + ", ".join(job.preferred_skills))
    if job.responsibilities:
        parts.append("Responsibilities: " + "; ".join(job.responsibilities))
    return _truncate("\n".join(parts))


def _truncate(text: str) -> str:
    """Embedding models have token limits, and an over-long input either
    errors or gets silently truncated by the provider. Truncating here makes
    the boundary explicit and predictable."""
    if len(text) <= MAX_EMBEDDING_CHARS:
        return text
    return text[:MAX_EMBEDDING_CHARS]
