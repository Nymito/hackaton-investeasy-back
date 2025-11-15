from datetime import datetime
from io import BytesIO
from textwrap import wrap
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from models import AnalyzeResponse


# ------------------------------------------------------------
#  PREMIUM STYLING
# ------------------------------------------------------------
PAGE_WIDTH, PAGE_HEIGHT = A4

MARGIN_X = 24 * mm
MARGIN_Y = 28 * mm
CONTENT_WIDTH = PAGE_WIDTH - (2 * MARGIN_X)

GRID = 16  # baseline spacing

COLOR_PRIMARY = colors.HexColor("#0F172A")    # consultant-dark
COLOR_ACCENT = colors.HexColor("#1D4ED8")     # corporate blue
COLOR_TEXT = colors.HexColor("#1E293B")       # slate
COLOR_MUTED = colors.HexColor("#64748B")
COLOR_BORDER = colors.HexColor("#CBD5E1")     # softer than before


# ------------------------------------------------------------
#  SPACING MANAGEMENT
# ------------------------------------------------------------
def ensure_space(pdf, y, need):
    """Guarantees vertical room, else starts new page."""
    if y - need <= MARGIN_Y:
        pdf.showPage()
        pdf.setFont("Helvetica", 10)
        return PAGE_HEIGHT - MARGIN_Y
    return y


# ------------------------------------------------------------
#  TEXT WRAPPING — baseline aligned
# ------------------------------------------------------------
def wrap_text(pdf, text, x, y, width, size=10, line_height=GRID):
    if not text:
        return y

    pdf.setFont("Helvetica", size)
    max_chars = int(width // (size * 0.51))

    for line in wrap(text, max_chars):
        y = ensure_space(pdf, y, line_height)
        y -= line_height
        pdf.drawString(x, y, line)

    return y


# ------------------------------------------------------------
#  SECTION TITLE — premium layout
# ------------------------------------------------------------
def section(pdf, title, y):
    y -= GRID
    y = ensure_space(pdf, y, GRID * 2)

    pdf.setFont("Helvetica-Bold", 13)
    pdf.setFillColor(COLOR_PRIMARY)
    pdf.drawString(MARGIN_X, y, title.upper())

    # subtle thin rule
    pdf.setStrokeColor(COLOR_BORDER)
    pdf.setLineWidth(0.7)
    pdf.line(MARGIN_X, y - 4, PAGE_WIDTH - MARGIN_X, y - 4)

    return y - (GRID + 4)  # 16 + offset


# ------------------------------------------------------------
#  BULLET LIST — pixel perfect alignment
# ------------------------------------------------------------
def bullet_list(pdf, items, x, y, width):
    bullet_indent = 12

    for item in items:
        lines = item.split("\n")
        for line in lines:
            y = ensure_space(pdf, y, GRID)

            # bullet baseline
            pdf.setFont("Helvetica", 10)
            pdf.drawString(x, y - GRID, "•")

            # text baseline aligned just below bullet
            y = wrap_text(pdf, line, x + bullet_indent, y, width, size=10, line_height=GRID)

        y -= 4  # slight spacing between bullet blocks

    return y


# ------------------------------------------------------------
#  SCORE GAUGE — clean & balanced
# ------------------------------------------------------------
def score_gauge(pdf, x, y, value):
    R = 38
    need = (R * 2) + GRID
    y = ensure_space(pdf, y, need)

    # base circle
    pdf.setLineWidth(4)
    pdf.setStrokeColor(COLOR_BORDER)
    pdf.arc(x - R, y - R, x + R, y + R, 0, 360)

    # score arc
    pdf.setStrokeColor(COLOR_ACCENT)
    pdf.arc(x - R, y - R, x + R, y + R, 90, -value * 3.6)

    # center text
    pdf.setFillColor(COLOR_PRIMARY)
    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawCentredString(x, y + 4, f"{value}/100")

    pdf.setFont("Helvetica", 8)
    pdf.setFillColor(COLOR_MUTED)
    pdf.drawCentredString(x, y - 11, "FEASIBILITY")

    return y - (R + 10)


# ------------------------------------------------------------
#  COMPETITOR TABLE — premium grid
# ------------------------------------------------------------
def competitor_table(pdf, analysis, y):
    comps = analysis.competitors or []
    if not comps:
        return wrap_text(pdf, "No competitors identified.", MARGIN_X, y, CONTENT_WIDTH)

    row_h = GRID * 2
    col = CONTENT_WIDTH

    for c in comps:
        y = ensure_space(pdf, y, row_h)

        # row box
        pdf.setStrokeColor(COLOR_BORDER)
        pdf.setLineWidth(0.8)
        pdf.rect(MARGIN_X, y - row_h, col, row_h, fill=0)

        # content
        pdf.setFont("Helvetica-Bold", 10)
        pdf.setFillColor(COLOR_PRIMARY)
        pdf.drawString(MARGIN_X + 8, y - 10, c.name)

        pdf.setFont("Helvetica", 9)
        pdf.setFillColor(COLOR_MUTED)
        pdf.drawString(MARGIN_X + col * 0.32, y - 12, f"S: {c.strength or 'N/A'}")
        pdf.drawString(MARGIN_X + col * 0.65, y - 12, f"W: {c.weakness or 'N/A'}")

        y -= row_h

    return y


# ------------------------------------------------------------
#  MAIN PREMIUM BUILDER
# ------------------------------------------------------------
def build_pdf_report(analysis: AnalyzeResponse) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)

    # HEADER
    pdf.setFont("Helvetica-Bold", 26)
    pdf.setFillColor(COLOR_PRIMARY)
    pdf.drawString(MARGIN_X, PAGE_HEIGHT - 48, "Market Feasibility Analysis")

    pdf.setFont("Helvetica", 11)
    pdf.setFillColor(COLOR_MUTED)
    pdf.drawString(
        MARGIN_X,
        PAGE_HEIGHT - 70,
        f"{analysis.category or 'General'} • Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
    )

    y = PAGE_HEIGHT - 100

    # SUMMARY
    y = section(pdf, "Summary", y)
    y = wrap_text(
        pdf,
        f"{analysis.summary}\n\nPositioning: {analysis.positioning}",
        MARGIN_X,
        y,
        CONTENT_WIDTH,
        size=11
    )

    y -= GRID

    # SCORE
    y = section(pdf, "Score & Overall Viability", y)
    gauge_center = MARGIN_X + 60
    y = score_gauge(pdf, gauge_center, y - 4, analysis.score.value)

    y = wrap_text(
        pdf,
        f"The project scores {analysis.score.value}/100. {analysis.score.reason}",
        MARGIN_X + 130,
        y + 42,  # position text block relative to gauge
        CONTENT_WIDTH - 140,
        size=11
    )

    y -= GRID

    # PROFITABILITY
    y = section(pdf, "Profitability & Financial Outlook", y)
    y = bullet_list(
        pdf,
        [
            f"Projected ROI: {analysis.profitability.roi_percentage}% over ~{analysis.profitability.timeframe_months} months.",
            analysis.profitability.reason,
        ],
        MARGIN_X,
        y,
        CONTENT_WIDTH
    )

    # TARGET
    y = section(pdf, "Target Market Analysis", y)
    y = wrap_text(
        pdf,
        f"Primary audience: {analysis.target.segment}. "
        f"Purchasing power: {analysis.target.purchasing_power}. "
        f"{analysis.target.justification}",
        MARGIN_X,
        y,
        CONTENT_WIDTH
    )

    y -= GRID

    # COMPETITORS
    y = section(pdf, "Competitor Landscape", y)
    y = competitor_table(pdf, analysis, y)
    y -= GRID

    # POSITIONING
    y = section(pdf, "Positioning Strategy", y)
    y = wrap_text(pdf, analysis.positioning, MARGIN_X, y, CONTENT_WIDTH)

    y -= GRID

    # SIMILAR
    y = section(pdf, "Similar Products/Services", y)
    sim = [
        f"{item.idea} ({round(item.similarity * 100)}% match)"
        for item in analysis.similar or []
    ] or ["No adjacent products identified."]
    y = bullet_list(pdf, sim, MARGIN_X, y, CONTENT_WIDTH)

    # CATEGORY
    y = section(pdf, "Category & Market Type", y)
    y = wrap_text(
        pdf,
        f"Category: {analysis.category or 'General'} • Market: Emerging and fragmented.",
        MARGIN_X,
        y,
        CONTENT_WIDTH
    )

    # FOOTER
    pdf.setStrokeColor(COLOR_BORDER)
    pdf.line(MARGIN_X, MARGIN_Y - 6, PAGE_WIDTH - MARGIN_X, MARGIN_Y - 6)

    pdf.setFont("Helvetica", 8)
    pdf.setFillColor(COLOR_MUTED)
    pdf.drawCentredString(PAGE_WIDTH / 2, MARGIN_Y - 18, "AI Market Analyst • Preliminary assessment")

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()
