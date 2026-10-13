"""The forecast as a spreadsheet or a PDF.

The spreadsheet keeps its working: the revenue and cost drivers are the engine's figures, and
every derived line (gross profit, operating costs, profit, tax-free cash, totals) is a formula, so
a founder can change a cost or a funding amount and watch cash move. Amounts are shown in major
units (all supported currencies have two decimal places).
"""

import io
from datetime import UTC, datetime
from html import escape as _escape
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.toolkit.forecasts import catalog, engine
from apps.toolkit.forecasts.models import Forecast

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_TYPE = "application/pdf"
NOTE = (
    "This forecast is calculated from the assumptions the founder entered. It is a planning "
    "tool, not a prediction, and is not audited or financial, legal or investment advice."
)
FIRST_COL = 2  # column B holds month 1


def document(
    venture_name: str, forecast: Forecast, results: dict[str, engine.Result]
) -> dict[str, Any]:
    return {
        "venture_name": venture_name,
        "version": forecast.version,
        "date": datetime.now(UTC).date().isoformat(),
        "assumptions": forecast.assumptions,
        "results": results,
    }


def _major(minor: int) -> float:
    return minor / 100


def _assumption_rows(a: dict[str, Any]) -> list[tuple[str, Any]]:
    info = {t["template"]: t for t in catalog.templates()}[a["template"]]
    labels = {d["name"]: d["label"] for d in info["drivers"]}
    rows: list[tuple[str, Any]] = [
        ("Revenue template", info["label"]),
        ("Currency", a["currency"]),
        ("Opening cash", _major(int(a.get("opening_cash_minor", 0)))),
        ("Tax rate (%)", a.get("tax_rate_pct", 0)),
    ]
    money_names = {d["name"] for d in info["drivers"] if d["kind"] == "money"}
    for name, value in (a.get("drivers") or {}).items():
        shown = _major(int(value)) if name in money_names else value
        rows.append((labels.get(name, name), shown))
    costs = a.get("costs") or {}
    rows.append(("Cost of sales (% of revenue)", costs.get("cogs_pct", 0)))
    rows.append(("Marketing per month", _major(int(costs.get("marketing_monthly_minor", 0)))))
    for role in costs.get("salaries", []):
        rows.append(
            (
                f"{role.get('role', 'Role')} (from month {role.get('start_month', 1)}, "
                f"x{role.get('count', 1)})",
                _major(int(role.get("monthly_minor", 0))),
            )
        )
    for item in costs.get("fixed", []):
        rows.append((item.get("label", "Fixed cost"), _major(int(item.get("monthly_minor", 0)))))
    for event in a.get("funding", []):
        rows.append(
            (
                f"{event.get('label', 'Funding')} (month {event.get('month', 1)})",
                _major(int(event.get("amount_minor", 0))),
            )
        )
    return rows


def render_xlsx(doc: dict[str, Any]) -> bytes:
    wb = Workbook()
    head = Font(bold=True)
    fill = PatternFill("solid", fgColor="EEEEEE")
    a = doc["assumptions"]
    currency = a["currency"]
    money_format = f'#,##0.00 "{currency}"'

    # Assumptions: the inputs, and the opening cash cell the monthly sheet points at.
    sheet = wb.active
    sheet.title = "Assumptions"
    sheet["A1"] = f"{doc['venture_name']}: financial forecast (version {doc['version']})"
    sheet["A1"].font = Font(bold=True, size=14)
    sheet["A2"] = NOTE
    for i, (label, value) in enumerate(_assumption_rows(a), start=4):
        sheet.cell(row=i, column=1, value=label)
        sheet.cell(row=i, column=2, value=value)
    sheet.column_dimensions["A"].width = 52
    sheet.column_dimensions["B"].width = 22
    opening_cell = "Assumptions!$B$6"  # third row of _assumption_rows

    for name, key in (
        ("Base", "base"),
        ("Conservative", "conservative"),
        ("Optimistic", "optimistic"),
    ):
        result: engine.Result = doc["results"][key]
        ws = wb.create_sheet(name)
        ws["A1"] = "Line"
        ws["A1"].font = head
        for m in result.months:
            cell = ws.cell(row=1, column=FIRST_COL + m.index - 1, value=f"Month {m.index}")
            cell.font = head
            cell.fill = fill
            cell.alignment = Alignment(horizontal="right")
        total_col = FIRST_COL + len(result.months)
        ws.cell(row=1, column=total_col, value="Total").font = head
        rows = [
            "Revenue",  # 2
            "Cost of sales",  # 3
            "Gross profit",  # 4 formula
            "Marketing",  # 5
            "Salaries",  # 6
            "Fixed costs",  # 7
            "Operating costs",  # 8 formula
            "Operating profit (EBITDA)",  # 9 formula
            "Tax",  # 10
            "Net income",  # 11 formula
            "Funding received",  # 12
            "Cash at month end",  # 13 formula
        ]
        for r, label in enumerate(rows, start=2):
            ws.cell(row=r, column=1, value=label)
        for m in result.months:
            c = FIRST_COL + m.index - 1
            col = get_column_letter(c)
            prev = get_column_letter(c - 1)
            ws.cell(row=2, column=c, value=_major(m.revenue))
            ws.cell(row=3, column=c, value=_major(m.cogs))
            ws.cell(row=4, column=c, value=f"={col}2-{col}3")
            ws.cell(row=5, column=c, value=_major(m.marketing))
            ws.cell(row=6, column=c, value=_major(m.salaries))
            ws.cell(row=7, column=c, value=_major(m.fixed))
            ws.cell(row=8, column=c, value=f"=SUM({col}5:{col}7)")
            ws.cell(row=9, column=c, value=f"={col}4-{col}8")
            ws.cell(row=10, column=c, value=_major(m.tax))
            ws.cell(row=11, column=c, value=f"={col}9-{col}10")
            ws.cell(row=12, column=c, value=_major(m.funding))
            start = opening_cell if m.index == 1 else f"{prev}13"
            ws.cell(row=13, column=c, value=f"={start}+{col}11+{col}12")
        first, last = get_column_letter(FIRST_COL), get_column_letter(total_col - 1)
        for r in (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12):
            ws.cell(row=r, column=total_col, value=f"=SUM({first}{r}:{last}{r})")
        ws.cell(row=13, column=total_col, value=f"={last}13")
        for row in ws.iter_rows(min_row=2, max_row=13, min_col=FIRST_COL, max_col=total_col):
            for cell in row:
                cell.number_format = money_format
        for r in (4, 9, 11, 13):
            ws.cell(row=r, column=1).font = head
        ws.column_dimensions["A"].width = 30
        ws.freeze_panes = "B2"
        # KPIs are counts, not money.
        kpi_names = sorted({k for m in result.months for k in m.kpis})
        for offset, kpi in enumerate(kpi_names, start=15):
            ws.cell(row=offset, column=1, value=kpi.replace("_", " ").capitalize())
            for m in result.months:
                ws.cell(row=offset, column=FIRST_COL + m.index - 1, value=m.kpis.get(kpi, 0))

    # Summary reads from the base sheet by formula and from the engine for the rest.
    summary = wb.create_sheet("Summary", 1)
    base: engine.Result = doc["results"]["base"]
    s = base.summary
    lines: list[tuple[str, Any, bool]] = [
        ("Revenue, year 1", "=SUM(Base!B2:M2)", True),
        ("Revenue, year 2", "=SUM(Base!N2:Y2)", True),
        ("Net income, year 1", "=SUM(Base!B11:M11)", True),
        ("Net income, year 2", "=SUM(Base!N11:Y11)", True),
        ("Lowest cash", "=MIN(Base!B13:Y13)", True),
        ("Cash at the end of month 24", "=Base!Y13", True),
        (
            "Break even month",
            s["break_even_month"] if s["break_even_month"] else "Not reached",
            False,
        ),
        (
            "Cash runs out in month",
            s["cash_out_month"] if s["cash_out_month"] else "Not within 24 months",
            False,
        ),
        ("Extra funding needed", _major(s["extra_funding_needed"]), True),
    ]
    for i, (label, value, is_money) in enumerate(lines, start=1):
        summary.cell(row=i, column=1, value=label).font = head
        cell = summary.cell(row=i, column=2, value=value)
        if is_money:
            cell.number_format = money_format
    row = len(lines) + 2
    summary.cell(row=row, column=1, value="Scenario comparison").font = head
    for j, title in enumerate(("Conservative", "Base", "Optimistic"), start=2):
        summary.cell(row=row, column=j, value=title).font = head
    for k, (label, key) in enumerate(
        (("Revenue, year 2", "revenue_year2"), ("Lowest cash", "lowest_cash")), start=1
    ):
        summary.cell(row=row + k, column=1, value=label)
        for j, scenario in enumerate(("conservative", "base", "optimistic"), start=2):
            cell = summary.cell(
                row=row + k, column=j, value=_major(doc["results"][scenario].summary[key])
            )
            cell.number_format = money_format
    for i, w in enumerate(base.warnings, start=row + 5):
        summary.cell(row=i, column=1, value=f"Check: {w['message']}")
    summary.column_dimensions["A"].width = 44
    summary.column_dimensions["B"].width = 24
    summary.column_dimensions["C"].width = 24
    summary.column_dimensions["D"].width = 24
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _escape_text(value: str) -> str:
    return _escape(value, quote=False)


def render_pdf(doc: dict[str, Any]) -> bytes:
    sheet = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=sheet["BodyText"], fontSize=8, leading=10)
    out = io.BytesIO()
    pdf = SimpleDocTemplate(
        out,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"{doc['venture_name']}: financial forecast",
        author=doc["venture_name"],
    )
    base: engine.Result = doc["results"]["base"]
    currency = doc["assumptions"]["currency"]

    def fmt(minor: int) -> str:
        return f"{minor / 100:,.0f}"

    story: list[Any] = [
        Paragraph(_escape_text(doc["venture_name"]), sheet["Title"]),
        Paragraph(
            f"Financial forecast, version {doc['version']}, {doc['date']} (amounts in {currency})",
            sheet["Heading2"],
        ),
        Paragraph(_escape_text(NOTE), small),
        Spacer(1, 5 * mm),
    ]
    s = base.summary
    headline = [
        ["", "Conservative", "Base", "Optimistic"],
        *[
            [label, *[fmt(doc["results"][sc].summary[key]) for sc in engine.SCENARIOS]]
            for label, key in (
                ("Revenue, year 1", "revenue_year1"),
                ("Revenue, year 2", "revenue_year2"),
                ("Net income, year 2", "net_income_year2"),
                ("Lowest cash", "lowest_cash"),
            )
        ],
    ]
    table = Table(headline, repeatRows=1)
    table.setStyle(
        TableStyle(
            [("GRID", (0, 0), (-1, -1), 0.4, "#999999"), ("BACKGROUND", (0, 0), (-1, 0), "#eeeeee")]
        )
    )
    story.append(table)
    story.append(Spacer(1, 4 * mm))
    be = s["break_even_month"]
    story.append(
        Paragraph(
            _escape_text(
                f"Break even: {'month ' + str(be) if be else 'not reached within 24 months'}. "
                + (
                    f"Cash runs out in month {s['cash_out_month']}; extra funding of "
                    f"{fmt(s['extra_funding_needed'])} would be needed."
                    if s["cash_out_month"]
                    else "Cash stays positive throughout."
                )
            ),
            sheet["BodyText"],
        )
    )
    for w in base.warnings:
        story.append(Paragraph(_escape_text("Check: " + w["message"]), small))
    story.append(PageBreak())
    story.append(Paragraph("Quarterly view (base case)", sheet["Heading2"]))
    quarters = [
        ["Quarter", "Revenue", "Gross profit", "Operating costs", "Net income", "Cash at end"]
    ]
    for q in range(8):
        chunk = base.months[q * 3 : q * 3 + 3]
        quarters.append(
            [
                f"Q{q % 4 + 1} year {q // 4 + 1}",
                fmt(sum(m.revenue for m in chunk)),
                fmt(sum(m.gross_profit for m in chunk)),
                fmt(sum(m.opex for m in chunk)),
                fmt(sum(m.net_income for m in chunk)),
                fmt(chunk[-1].cash_end),
            ]
        )
    qt = Table(quarters, repeatRows=1)
    qt.setStyle(
        TableStyle(
            [("GRID", (0, 0), (-1, -1), 0.4, "#999999"), ("BACKGROUND", (0, 0), (-1, 0), "#eeeeee")]
        )
    )
    story.append(qt)
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Assumptions", sheet["Heading2"]))
    rows = [[label, str(value)] for label, value in _assumption_rows(doc["assumptions"])]
    at = Table(rows, colWidths=[110 * mm, 60 * mm])
    at.setStyle(
        TableStyle([("GRID", (0, 0), (-1, -1), 0.3, "#bbbbbb"), ("FONTSIZE", (0, 0), (-1, -1), 8)])
    )
    story.append(at)
    pdf.build(story)
    return out.getvalue()
