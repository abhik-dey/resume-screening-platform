"""
PDF rendering for recruiter reports.

Infrastructure, not domain: it depends on reportlab and produces bytes.
The data it renders is assembled separately (domain/report/builder.py), so
layout changes never touch aggregation logic and vice versa.

DESIGN NOTE — why the advisory notice appears on every single page:
this PDF is the artifact most likely to be forwarded, printed, or read by
someone who never touched the API. Every caveat the system attaches in JSON
disappears the moment a page is printed in isolation. Putting the notice in
the page footer means it survives partial printing and photocopying.
"""
import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.domain.feedback.recommendation import ADVISORY_NOTICE
from app.domain.report.builder import ReportData

_HEADER_COLOR = colors.HexColor("#0f3460")
_ALT_ROW_COLOR = colors.HexColor("#f2f4fa")
_MUTED = colors.HexColor("#666666")

# Short form for the page footer; the full notice appears on page 1.
_FOOTER_NOTICE = (
    "Automated screening aid — advisory only, not a hiring decision. "
    "Review alongside the full application."
)


def _escape(text: str | None) -> str:
    """reportlab's Paragraph parses a subset of HTML, so raw text from
    resumes and LLM output must be escaped or a stray '&' or '<' breaks
    rendering (or worse, is interpreted as markup)."""
    if text is None:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _draw_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(_MUTED)
    canvas.drawString(0.75 * inch, 0.5 * inch, _FOOTER_NOTICE)
    canvas.drawRightString(letter[0] - 0.75 * inch, 0.5 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle", parent=base["Title"], fontSize=20, textColor=_HEADER_COLOR, spaceAfter=6
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=base["Normal"],
            fontSize=11,
            textColor=_MUTED,
            alignment=TA_CENTER,
            spaceAfter=18,
        ),
        "h1": ParagraphStyle(
            "ReportH1",
            parent=base["Heading1"],
            fontSize=14,
            textColor=_HEADER_COLOR,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "ReportH2",
            parent=base["Heading2"],
            fontSize=11,
            textColor=_HEADER_COLOR,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "ReportBody", parent=base["Normal"], fontSize=9.5, leading=14, spaceAfter=6
        ),
        "small": ParagraphStyle(
            "ReportSmall", parent=base["Normal"], fontSize=8, leading=11, textColor=_MUTED
        ),
        "cell": ParagraphStyle("ReportCell", parent=base["Normal"], fontSize=8, leading=10),
        "notice": ParagraphStyle(
            "ReportNotice",
            parent=base["Normal"],
            fontSize=8.5,
            leading=12,
            leftIndent=8,
            rightIndent=8,
            backColor=colors.HexColor("#fff8e1"),
            borderColor=colors.HexColor("#f0c419"),
            borderWidth=0.75,
            borderPadding=8,
            spaceBefore=8,
            spaceAfter=12,
        ),
    }


def render_report_pdf(data: ReportData, generated_by_email: str | None = None) -> bytes:
    """Render a ReportData structure to PDF bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.85 * inch,
        title=f"Candidate Report — {data.job_title}",
    )
    s = _styles()
    story = []

    # --- Page 1: overview ---
    story.append(Paragraph("Candidate Screening Report", s["title"]))
    story.append(Paragraph(_escape(data.job_title), s["subtitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=_HEADER_COLOR, spaceAfter=10))

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    meta = f"Generated {generated_at}"
    if generated_by_email:
        meta += f" by {_escape(generated_by_email)}"
    story.append(Paragraph(meta, s["small"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph(ADVISORY_NOTICE, s["notice"]))

    story.append(Paragraph("Role Requirements", s["h1"]))
    requirement_rows = [
        ["Required skills", ", ".join(data.required_skills) or "None specified"],
        ["Preferred skills", ", ".join(data.preferred_skills) or "None specified"],
        [
            "Minimum experience",
            f"{data.min_experience_years} years"
            if data.min_experience_years is not None
            else "Not specified",
        ],
        ["Education", data.education_requirement or "Not specified"],
    ]
    requirement_table_rows = [["Requirement", "Detail"]] + [
        [r[0], Paragraph(_escape(r[1]), s["cell"])] for r in requirement_rows
    ]
    story.append(_make_table(requirement_table_rows, col_widths=[1.5 * inch, 5.25 * inch]))

    story.append(Paragraph("Screening Overview", s["h1"]))
    overview_rows = [
        ["Candidates screened", str(data.total_candidates)],
        ["Average match score", f"{data.average_score:.2f}"],
    ]
    for label, count in sorted(data.recommendation_counts.items()):
        overview_rows.append([label, str(count)])
    story.append(
        _make_table(
            [["Metric", "Value"]] + overview_rows, col_widths=[3.0 * inch, 3.75 * inch]
        )
    )

    if data.executive_summary:
        story.append(Paragraph("Executive Summary", s["h1"]))
        story.append(Paragraph(_escape(data.executive_summary), s["body"]))
    elif data.summary_generation_failed:
        story.append(Paragraph("Executive Summary", s["h1"]))
        story.append(
            Paragraph(
                "The narrative summary could not be generated for this report. All candidate "
                "data below is complete and unaffected.",
                s["small"],
            )
        )

    story.append(
        Paragraph(
            "Match scores are computed arithmetically from skills, experience, and education "
            "against the stated requirements. They reflect resume-to-requirements fit only.",
            s["small"],
        )
    )

    # --- Page 2: comparison table ---
    story.append(PageBreak())
    story.append(Paragraph("Candidate Ranking", s["h1"]))

    if not data.candidates:
        story.append(
            Paragraph("No scored candidates for this role yet.", s["body"])
        )
    else:
        header = ["Rank", "Candidate", "Score", "Recommendation", "Missing required skills"]
        rows = [header]
        for c in data.candidates:
            rows.append(
                [
                    str(c.rank) if c.rank is not None else "—",
                    Paragraph(_escape(c.candidate_name), s["cell"]),
                    f"{c.similarity_score:.2f}",
                    c.recommendation_label or "Not assessed",
                    Paragraph(_escape(", ".join(c.missing_skills)) or "None", s["cell"]),
                ]
            )
        story.append(
            _make_table(rows, col_widths=[0.5 * inch, 1.7 * inch, 0.6 * inch, 1.35 * inch, 2.6 * inch])
        )

    # --- Per-candidate detail ---
    for candidate in data.candidates:
        story.append(PageBreak())
        rank_prefix = f"#{candidate.rank} — " if candidate.rank is not None else ""
        story.append(Paragraph(f"{rank_prefix}{_escape(candidate.candidate_name)}", s["h1"]))

        detail_rows = [
            ["Match score", f"{candidate.similarity_score:.2f}"],
            ["Recommendation", candidate.recommendation_label or "Not assessed"],
            ["Resume file", candidate.resume_filename],
        ]
        if candidate.candidate_email:
            detail_rows.insert(0, ["Email", candidate.candidate_email])
        story.append(
            _make_table(
                [["Field", "Value"]]
                + [[r[0], Paragraph(_escape(r[1]), s["cell"])] for r in detail_rows],
                col_widths=[1.5 * inch, 5.25 * inch],
            )
        )

        if candidate.threshold_rationale:
            story.append(Paragraph("Why this recommendation", s["h2"]))
            story.append(Paragraph(_escape(candidate.threshold_rationale), s["body"]))

        if candidate.summary:
            story.append(Paragraph("Summary", s["h2"]))
            story.append(Paragraph(_escape(candidate.summary), s["body"]))

        _add_bullet_section(story, s, "Matched skills", candidate.matched_skills)
        _add_bullet_section(story, s, "Missing skills", candidate.missing_skills)
        _add_bullet_section(story, s, "Strengths", candidate.strengths)
        _add_bullet_section(story, s, "Areas of concern", candidate.weaknesses)
        _add_bullet_section(story, s, "Risk factors", candidate.risk_factors)

    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return buffer.getvalue()


def _add_bullet_section(story: list, s: dict, heading: str, items: list[str]) -> None:
    if not items:
        return
    story.append(Paragraph(heading, s["h2"]))
    for item in items:
        story.append(Paragraph(f"&bull;&nbsp;&nbsp;{_escape(item)}", s["body"]))


def _make_table(rows: list, col_widths: list) -> Table:
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _HEADER_COLOR),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ALT_ROW_COLOR]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table
