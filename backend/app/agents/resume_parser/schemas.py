"""
Structured output schema for the Resume Parsing Agent's LLM call.

Kept separate from the Resume domain entity / ORM model deliberately: this
schema describes what we ask the LLM to return, not how a resume is
persisted. All fields are optional/defaulted because LLM extraction is
inherently best-effort — a resume missing a phone number shouldn't fail
the whole parse.
"""
from pydantic import BaseModel, Field


class EducationEntry(BaseModel):
    institution: str
    degree: str | None = None
    field_of_study: str | None = None
    start_year: int | None = None
    end_year: int | None = None


class ExperienceEntry(BaseModel):
    company: str
    title: str
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None


class ProjectEntry(BaseModel):
    name: str
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)


class CertificateEntry(BaseModel):
    name: str
    issuer: str | None = None
    year: int | None = None


class ParsedResumeOutput(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    education: list[EducationEntry] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    # Raw extracted skill strings, not yet normalized/categorized — that's
    # the Skill Extraction Agent's job (Phase 7), not this agent's.
    skills: list[str] = Field(default_factory=list)
    certificates: list[CertificateEntry] = Field(default_factory=list)
    links: dict[str, str] = Field(default_factory=dict)
