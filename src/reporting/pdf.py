"""Portable Markdown-to-PDF renderer for scheduled research artifacts.

The renderer uses ReportLab's built-in fonts and normalizes unsupported typographic
characters so PDF generation works on Linux GitHub runners and Windows developers' PCs.
"""
import re
import unicodedata
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def _ascii_safe(value: str) -> str:
    value = (value or "").replace("₹", "INR ").replace("—", "-").replace("–", "-").replace("…", "...")
    value = value.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")


def _inline_markup(value: str) -> str:
    """Escape untrusted report text, then apply a small safe Markdown subset."""
    safe = escape(_ascii_safe(value))
    safe = re.sub(
        r"\[([^\]]+)\]\((https://[^\s)]+)\)",
        lambda match: f'<link href="{match.group(2)}" color="#1D4ED8">{match.group(1)}</link>',
        safe,
    )
    # Long naked exchange URLs can overflow ReportLab Paragraphs. Keep the exact
    # destination clickable while displaying a compact, readable label.
    safe = re.sub(
        r"(?<![=\"'>])(https://[^\s<]+)",
        lambda match: (
            f'<link href="{match.group(1).rstrip(".,;")}" color="#1D4ED8">'
            f'{escape(match.group(1).rstrip(".,;")[:58])}'
            f'{"..." if len(match.group(1).rstrip(".,;")) > 58 else ""}</link>'
        ),
        safe,
    )
    safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)
    safe = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", safe)
    return safe


def markdown_to_pdf(markdown_text: str, output_path: str | Path, *, title: str = "Research Report") -> Path:
    """Render headings, bullets, paragraphs, and links to a compact PDF."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=18, leading=22, alignment=TA_LEFT, textColor=colors.HexColor("#12345A"),
        spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        name="ReportHeading2", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=13, leading=16, spaceBefore=8, spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="ReportHeading3", parent=styles["Heading3"], fontName="Helvetica-Bold",
        fontSize=10, leading=13, spaceBefore=6, spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name="ReportBody", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=8.5, leading=11.5, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="ReportQuote", parent=styles["BodyText"], fontName="Helvetica-Oblique",
        fontSize=8, leading=10, leftIndent=12, textColor=colors.HexColor("#374151"),
        spaceBefore=2, spaceAfter=5,
    ))

    story = []
    for raw_line in (markdown_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 3))
        elif line.startswith("# "):
            story.append(Paragraph(_inline_markup(line[2:]), styles["ReportTitle"]))
        elif line.startswith("## "):
            story.append(Paragraph(_inline_markup(line[3:]), styles["ReportHeading2"]))
        elif line.startswith("### "):
            story.append(Paragraph(_inline_markup(line[4:]), styles["ReportHeading3"]))
        elif line.startswith("- ") or line.startswith("* "):
            story.append(Paragraph("&#8226; " + _inline_markup(line[2:]), styles["ReportBody"]))
        elif line.startswith("> "):
            story.append(Paragraph(_inline_markup(line[2:]), styles["ReportQuote"]))
        elif line.startswith("---"):
            story.append(Spacer(1, 6))
        else:
            story.append(Paragraph(_inline_markup(line), styles["ReportBody"]))

    document = SimpleDocTemplate(
        str(destination), pagesize=A4,
        rightMargin=17 * mm, leftMargin=17 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=_ascii_safe(title)[:200],
        author="IPO-Analysis",
    )
    document.build(story)
    return destination
