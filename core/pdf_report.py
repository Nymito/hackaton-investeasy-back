from datetime import datetime
from io import BytesIO
from textwrap import wrap
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from models import AnalyzeResponse


PAGE_WIDTH, PAGE_HEIGHT = A4

MARGIN_X = 24 * mm
MARGIN_Y = 28 * mm
CONTENT_WIDTH = PAGE_WIDTH - (2 * MARGIN_X)

GRID = 16  # baseline spacing

COLOR_PRIMARY = colors.HexColor("#0F172A")
COLOR_ACCENT = colors.HexColor("#1D4ED8")
COLOR_TEXT = colors.HexColor("#1E293B")
COLOR_MUTED = colors.HexColor("#64748B")
COLOR_BORDER = colors.HexColor("#CBD5E1")

BULLET_GLYPH = "\u2022"
SCORE_RADIUS = 38


class PdfReportBuilder:
    """Lightweight helper that keeps a single canvas instance alive."""

    def __init__(self, analysis: AnalyzeResponse):
        self.analysis = analysis
        self.buffer = BytesIO()
        self.pdf = canvas.Canvas(self.buffer, pagesize=A4)

    # -- spacing helpers -------------------------------------------------
    def _ensure_space(self, y: float, needed: float) -> float:
        if y - needed <= MARGIN_Y:
            self.pdf.showPage()
            self.pdf.setFont("Helvetica", 10)
            return PAGE_HEIGHT - MARGIN_Y
        return y

    def _wrap_lines(self, text: str, width: float, size: int) -> list[str]:
        if not text:
            return []
        max_chars = int(width // (size * 0.51))
        return wrap(text, max_chars)

    def _wrap_text(self, text: str, x: float, y: float, width: float, size: int = 10, line_height: int = GRID) -> float:
        if not text:
            return y

        lines = self._wrap_lines(text, width, size)
        self.pdf.setFont("Helvetica", size)

        for line in lines:
            y = self._ensure_space(y, line_height)
            y -= line_height
            self.pdf.drawString(x, y, line)

        return y

    def _section(self, title: str, y: float) -> float:
        y -= GRID
        y = self._ensure_space(y, GRID * 2)

        self.pdf.setFont("Helvetica-Bold", 13)
        self.pdf.setFillColor(COLOR_PRIMARY)
        self.pdf.drawString(MARGIN_X, y, title.upper())

        self.pdf.setStrokeColor(COLOR_BORDER)
        self.pdf.setLineWidth(0.7)
        self.pdf.line(MARGIN_X, y - 4, PAGE_WIDTH - MARGIN_X, y - 4)

        return y - (GRID + 4)

    def _bullet_list(self, items, x: float, y: float, width: float) -> float:
        bullet_indent = 12

        for item in items:
            lines = item.split("\n")
            for line in lines:
                y = self._ensure_space(y, GRID)
                self.pdf.setFont("Helvetica", 10)
                self.pdf.drawString(x, y - GRID, BULLET_GLYPH)
                y = self._wrap_text(line, x + bullet_indent, y, width, size=10, line_height=GRID)
            y -= 4

        return y

    def _score_gauge(self, x: float, center_y: float, value: int) -> None:
        self.pdf.setLineWidth(4)
        self.pdf.setStrokeColor(COLOR_BORDER)
        self.pdf.arc(
            x - SCORE_RADIUS,
            center_y - SCORE_RADIUS,
            x + SCORE_RADIUS,
            center_y + SCORE_RADIUS,
            0,
            360,
        )

        self.pdf.setStrokeColor(COLOR_ACCENT)
        self.pdf.arc(
            x - SCORE_RADIUS,
            center_y - SCORE_RADIUS,
            x + SCORE_RADIUS,
            center_y + SCORE_RADIUS,
            90,
            -value * 3.6,
        )

        self.pdf.setFillColor(COLOR_PRIMARY)
        self.pdf.setFont("Helvetica-Bold", 15)
        self.pdf.drawCentredString(x, center_y + 4, f"{value}/100")

        self.pdf.setFont("Helvetica", 8)
        self.pdf.setFillColor(COLOR_MUTED)
        self.pdf.drawCentredString(x, center_y - 11, "FEASIBILITY")

    def _competitor_table(self, y: float) -> float:
        competitors = self.analysis.competitors or []
        if not competitors:
            return self._wrap_text("No competitors identified.", MARGIN_X, y, CONTENT_WIDTH)

        row_h = GRID * 2
        col = CONTENT_WIDTH

        for competitor in competitors:
            y = self._ensure_space(y, row_h)

            self.pdf.setStrokeColor(COLOR_BORDER)
            self.pdf.setLineWidth(0.8)
            self.pdf.rect(MARGIN_X, y - row_h, col, row_h, fill=0)

            self.pdf.setFont("Helvetica-Bold", 10)
            self.pdf.setFillColor(COLOR_PRIMARY)
            self.pdf.drawString(MARGIN_X + 8, y - 10, competitor.name)

            self.pdf.setFont("Helvetica", 9)
            self.pdf.setFillColor(COLOR_MUTED)
            self.pdf.drawString(MARGIN_X + col * 0.32, y - 12, f"S: {competitor.strength or 'N/A'}")
            self.pdf.drawString(MARGIN_X + col * 0.65, y - 12, f"W: {competitor.weakness or 'N/A'}")

            y -= row_h

        return y

    def _draw_header(self) -> None:
        self.pdf.setFont("Helvetica-Bold", 26)
        self.pdf.setFillColor(COLOR_PRIMARY)
        self.pdf.drawString(MARGIN_X, PAGE_HEIGHT - 48, "Market Feasibility Analysis")

        self.pdf.setFont("Helvetica", 11)
        self.pdf.setFillColor(COLOR_MUTED)
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        subtitle = f"{self.analysis.category or 'General'} {BULLET_GLYPH} Generated {timestamp}"
        self.pdf.drawString(MARGIN_X, PAGE_HEIGHT - 70, subtitle)

    def _draw_footer(self) -> None:
        self.pdf.setStrokeColor(COLOR_BORDER)
        self.pdf.line(MARGIN_X, MARGIN_Y - 6, PAGE_WIDTH - MARGIN_X, MARGIN_Y - 6)

        self.pdf.setFont("Helvetica", 8)
        self.pdf.setFillColor(COLOR_MUTED)
        footer = f"AI Market Analyst {BULLET_GLYPH} Preliminary assessment"
        self.pdf.drawCentredString(PAGE_WIDTH / 2, MARGIN_Y - 18, footer)

    def _score_details(self, y: float) -> float:
        analysis = self.analysis
        text_x = MARGIN_X + (SCORE_RADIUS * 2) + 40
        text_width = CONTENT_WIDTH - (text_x - MARGIN_X)
        body = f"The project scores {analysis.score.value}/100. {analysis.score.reason}"
        lines = self._wrap_lines(body, text_width, size=11)
        text_height = max(1, len(lines)) * GRID
        block_height = max(SCORE_RADIUS * 2, text_height)
        y = self._ensure_space(y, block_height)

        top = y
        center_y = top - SCORE_RADIUS
        gauge_x = MARGIN_X + SCORE_RADIUS
        self._score_gauge(gauge_x, center_y, analysis.score.value)

        self.pdf.setFont("Helvetica", 11)
        text_y = top
        for line in lines:
            text_y -= GRID
            self.pdf.drawString(text_x, text_y, line)

        return min(center_y - SCORE_RADIUS, text_y)

    # -- public API ------------------------------------------------------
    def build(self) -> bytes:
        analysis = self.analysis
        y = PAGE_HEIGHT - 100

        self._draw_header()

        y = self._section("Summary", y)
        y = self._wrap_text(
            f"{analysis.summary}\n\nPositioning: {analysis.positioning}",
            MARGIN_X,
            y,
            CONTENT_WIDTH,
            size=11,
        )
        y -= GRID

        y = self._section("Score & Overall Viability", y)
        y = self._score_details(y)
        y -= GRID

        y = self._section("Profitability & Financial Outlook", y)
        y = self._bullet_list(
            [
                f"Projected ROI: {analysis.profitability.roi_percentage}% over ~{analysis.profitability.timeframe_months} months.",
                analysis.profitability.reason,
            ],
            MARGIN_X,
            y,
            CONTENT_WIDTH,
        )

        y = self._section("Target Market Analysis", y)
        y = self._wrap_text(
            f"Primary audience: {analysis.target.segment}. "
            f"Purchasing power: {analysis.target.purchasing_power}. "
            f"{analysis.target.justification}",
            MARGIN_X,
            y,
            CONTENT_WIDTH,
        )
        y -= GRID

        y = self._section("Competitor Landscape", y)
        y = self._competitor_table(y)
        y -= GRID

        y = self._section("Positioning Strategy", y)
        y = self._wrap_text(analysis.positioning, MARGIN_X, y, CONTENT_WIDTH)
        y -= GRID

        y = self._section("Similar Products/Services", y)
        similar = [
            f"{item.idea} ({round(item.similarity * 100)}% match)" for item in analysis.similar or []
        ] or ["No adjacent products identified."]
        y = self._bullet_list(similar, MARGIN_X, y, CONTENT_WIDTH)

        y = self._section("Category & Market Type", y)
        y = self._wrap_text(
            f"Category: {analysis.category or 'General'} {BULLET_GLYPH} Market: Emerging and fragmented.",
            MARGIN_X,
            y,
            CONTENT_WIDTH,
        )

        self._draw_footer()

        self.pdf.save()
        self.buffer.seek(0)
        return self.buffer.getvalue()


def build_pdf_report(analysis: AnalyzeResponse) -> bytes:
    return PdfReportBuilder(analysis).build()
