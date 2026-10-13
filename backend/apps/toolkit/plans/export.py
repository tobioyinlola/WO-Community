"""Rendering a plan to a Word document or a PDF.

Only the member's saved text is rendered; nothing is generated here. Sections with no text are
left out (the readiness check says what is missing), citations appear as numbered sources at the
end of each section, and a short note says what the document is and is not.
"""

import io
from datetime import UTC, datetime
from html import escape as _escape
from typing import Any

from docx import Document
from docx.shared import Pt
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def escape(value: str) -> str:
    """Text for a PDF paragraph, which reads a small markup of its own."""
    return _escape(value, quote=False)


NOTE = (
    "This business plan was written from the information in the founder's venture profile and "
    "from the public sources listed under each section. It is not audited, and it is not "
    "financial, legal or investment advice."
)
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_TYPE = "application/pdf"


def _marks(cites: list[int]) -> str:
    return " " + "".join(f"[{n}]" for n in cites) if cites else ""


def render_docx(plan: dict[str, Any]) -> bytes:
    doc = Document()
    doc.core_properties.title = f"{plan['venture_name']}: business plan"
    doc.core_properties.author = plan["venture_name"]
    doc.add_heading(plan["venture_name"], level=0)
    doc.add_paragraph("Business plan")
    doc.add_paragraph(f"Version {plan['version']}, {plan['date']}")
    doc.add_paragraph(NOTE).runs[0].italic = True
    chapter = ""
    for section in plan["sections"]:
        if section["chapter"] != chapter:
            chapter = section["chapter"]
            doc.add_heading(chapter, level=1)
        doc.add_heading(section["title"], level=2)
        for block in section["blocks"]:
            kind = block["type"]
            if kind == "heading":
                doc.add_heading(block["text"], level=3)
            elif kind == "paragraph":
                doc.add_paragraph(block["text"] + _marks(block.get("cites", [])))
            elif kind == "bullets":
                for item in block["items"]:
                    doc.add_paragraph(item, style="List Bullet")
                if block.get("cites"):
                    doc.add_paragraph(_marks(block["cites"]).strip())
            elif kind == "table":
                table = doc.add_table(rows=1, cols=len(block["columns"]))
                table.style = "Light Grid Accent 1"
                for i, name in enumerate(block["columns"]):
                    table.rows[0].cells[i].text = name
                for row in block["rows"]:
                    cells = table.add_row().cells
                    for i, value in enumerate(row):
                        cells[i].text = value
        if section["citations"]:
            para = doc.add_paragraph()
            para.add_run("Sources").bold = True
            for c in section["citations"]:
                line = doc.add_paragraph(style="List Number")
                run = line.add_run(f"{c['source_name'] or c['url']}, {c['date']}. {c['url']}")
                run.font.size = Pt(9)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def render_pdf(plan: dict[str, Any]) -> bytes:
    sheet = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=sheet["BodyText"], fontSize=8, leading=10)
    out = io.BytesIO()
    doc = SimpleDocTemplate(
        out,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f"{plan['venture_name']}: business plan",
        author=plan["venture_name"],
    )
    story: list[Any] = [
        Paragraph(escape(plan["venture_name"]), sheet["Title"]),
        Paragraph("Business plan", sheet["Heading2"]),
        Paragraph(f"Version {plan['version']}, {plan['date']}", sheet["BodyText"]),
        Spacer(1, 6 * mm),
        Paragraph(escape(NOTE), small),
        PageBreak(),
    ]
    chapter = ""
    for section in plan["sections"]:
        if section["chapter"] != chapter:
            chapter = section["chapter"]
            story.append(Paragraph(escape(chapter), sheet["Heading1"]))
        story.append(Paragraph(escape(section["title"]), sheet["Heading2"]))
        for block in section["blocks"]:
            kind = block["type"]
            if kind == "heading":
                story.append(Paragraph(escape(block["text"]), sheet["Heading3"]))
            elif kind == "paragraph":
                text = escape(block["text"]) + escape(_marks(block.get("cites", [])))
                story.append(Paragraph(text, sheet["BodyText"]))
            elif kind == "bullets":
                items = [ListItem(Paragraph(escape(i), sheet["BodyText"])) for i in block["items"]]
                story.append(ListFlowable(items, bulletType="bullet"))
            elif kind == "table":
                data = [block["columns"], *block["rows"]]
                cells = [[Paragraph(escape(str(c)), small) for c in row] for row in data]
                table = Table(cells, repeatRows=1)
                table.setStyle(
                    TableStyle(
                        [
                            ("GRID", (0, 0), (-1, -1), 0.4, "#999999"),
                            ("BACKGROUND", (0, 0), (-1, 0), "#eeeeee"),
                        ]
                    )
                )
                story.append(table)
            story.append(Spacer(1, 2 * mm))
        for c in section["citations"]:
            line = f"[{c['number']}] {c['source_name'] or ''} ({c['date']}) {c['url']}"
            story.append(Paragraph(escape(line), small))
        story.append(Spacer(1, 4 * mm))
    doc.build(story)
    return out.getvalue()


def document(venture_name: str, version: int, sections: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "venture_name": venture_name,
        "version": version,
        "date": datetime.now(UTC).date().isoformat(),
        "sections": sections,
    }
