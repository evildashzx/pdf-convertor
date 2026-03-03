#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Lead magnet PDF generator:
The 5 Strategy-Killing Mistakes Amazon Sellers Make in Niche Selection.
"""

from pathlib import Path

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Circle, Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

TITLE = "The 5 Strategy-Killing Mistakes Amazon Sellers Make in Niche Selection"
SUBTITLE = "A Data-Driven Guide to Avoiding $10,000+ Launch Failures."

# Premium minimalist palette
PALETTE = {
    "bg": colors.HexColor("#F8FAFC"),
    "ink": colors.HexColor("#0F172A"),
    "muted": colors.HexColor("#475569"),
    "accent": colors.HexColor("#1D4ED8"),
    "danger_bg": colors.HexColor("#FEE2E2"),
    "danger_ink": colors.HexColor("#B91C1C"),
    "line": colors.HexColor("#CBD5E1"),
}


def _chart_histogram() -> Drawing:
    """Create example product maturity distribution chart."""
    drawing = Drawing(460, 210)
    drawing.add(String(5, 195, "Product Maturity Distribution (Example)", fontName="Helvetica-Bold", fontSize=10))

    chart = VerticalBarChart()
    chart.x = 45
    chart.y = 45
    chart.height = 120
    chart.width = 380
    chart.data = [[42, 9, 5, 3, 2]]
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 45
    chart.valueAxis.valueStep = 5
    chart.categoryAxis.categoryNames = ["0-50", "51-200", "201-500", "501-1000", "1001+"]
    chart.bars[0].fillColor = colors.HexColor("#3B82F6")
    chart.bars[0].strokeColor = colors.HexColor("#1E3A8A")
    drawing.add(chart)
    drawing.add(String(45, 28, "Review Buckets", fontSize=8, fillColor=colors.HexColor("#334155")))
    drawing.add(String(300, 168, "Large low-review cluster", fontSize=7, fillColor=colors.HexColor("#1E3A8A")))
    drawing.add(String(355, 62, "Dinosaurs", fontSize=7, fillColor=colors.HexColor("#7C2D12")))
    return drawing


def _chart_scatter() -> Drawing:
    """Create example price vs revenue scatter chart."""
    drawing = Drawing(460, 210)
    drawing.add(String(5, 195, "Price vs Estimated Revenue (Example)", fontName="Helvetica-Bold", fontSize=10))

    # plot area
    x0, y0, w, h = 45, 40, 380, 130
    drawing.add(Rect(x0, y0, w, h, strokeColor=colors.HexColor("#94A3B8"), fillColor=None))

    prices = [11, 13, 15, 17, 19, 22, 24, 28, 32, 37, 42, 46]
    revenue_k = [8, 9, 11, 12, 10, 14, 15, 17, 27, 30, 26, 22]

    min_p, max_p = 10, 50
    min_r, max_r = 0, 32

    def sx(p):
        return x0 + (p - min_p) / (max_p - min_p) * w

    def sy(r):
        return y0 + (r - min_r) / (max_r - min_r) * h

    for p, r in zip(prices, revenue_k):
        drawing.add(Circle(sx(p), sy(r), 3.3, fillColor=colors.HexColor("#2563EB"), strokeColor=colors.HexColor("#1D4ED8")))

    hp, hr = 37, 30
    drawing.add(Circle(sx(hp), sy(hr), 4.8, fillColor=colors.HexColor("#DC2626"), strokeColor=colors.HexColor("#B91C1C")))
    drawing.add(String(sx(hp) + 8, sy(hr) + 8, "Premium outlier", fontSize=7, fillColor=colors.HexColor("#B91C1C")))

    drawing.add(String(45, 25, "Price ($)", fontSize=8, fillColor=colors.HexColor("#334155")))
    drawing.add(String(280, 25, "Estimated Monthly Revenue ($K)", fontSize=8, fillColor=colors.HexColor("#334155")))
    drawing.add(Line(x0, y0, x0 + w, y0, strokeColor=colors.HexColor("#94A3B8")))
    drawing.add(Line(x0, y0, x0, y0 + h, strokeColor=colors.HexColor("#94A3B8")))

    return drawing


def _logo_path() -> Path | None:
    for candidate in ("icon.png", "analytics_logo.png", "logo.png"):
        p = Path(candidate)
        if p.exists():
            return p
    return None


def build_pdf(output_file: str = "amazon_seller_strategy_guide.pdf", company_name: str = "Your Company Name") -> None:
    doc = SimpleDocTemplate(
        output_file,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.6 * cm,
        title=TITLE,
        author=company_name,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleMain", parent=styles["Title"], fontSize=26, leading=32, textColor=PALETTE["ink"]))
    styles.add(ParagraphStyle(name="Subtitle", parent=styles["Normal"], fontSize=13, leading=18, textColor=PALETTE["muted"]))
    styles.add(ParagraphStyle(name="Header", parent=styles["Heading1"], fontSize=20, leading=24, textColor=PALETTE["ink"]))
    styles.add(ParagraphStyle(name="Body", parent=styles["BodyText"], fontSize=11, leading=16, textColor=PALETTE["ink"]))
    styles.add(ParagraphStyle(name="Insight", parent=styles["BodyText"], fontSize=11, leading=16, textColor=PALETTE["accent"]))

    story = []

    # Page 1 - Title page
    logo = _logo_path()
    if logo:
        story.append(Image(str(logo), width=4.2 * cm, height=4.2 * cm))
    else:
        story.append(Paragraph("<b>Analytics</b>", styles["Header"]))
    story.append(Spacer(1, 1.4 * cm))
    story.append(Paragraph(TITLE, styles["TitleMain"]))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(SUBTITLE, styles["Subtitle"]))
    story.append(Spacer(1, 14.5 * cm))
    story.append(Paragraph(f"Free Strategy Insights | {company_name}", styles["Subtitle"]))
    story.append(PageBreak())

    # Page 2 - Mistake #1
    story.append(Paragraph("Mistake #1 — Ignoring the Saturation Index (CR3)", styles["Header"]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        "Many sellers look at high total revenue but ignore who controls it. "
        "If the Top 3 brands control &gt;70% (CR3), you are fighting for crumbs.",
        styles["Body"],
    ))
    story.append(Spacer(1, 0.5 * cm))

    cr3_table = Table(
        [["Metric", "Value", "Risk"], ["CR3 (Top 3 Brand Share)", "82%", "High Risk"]],
        colWidths=[7 * cm, 3 * cm, 4 * cm],
    )
    cr3_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PALETTE["bg"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), PALETTE["ink"]),
        ("GRID", (0, 0), (-1, -1), 0.5, PALETTE["line"]),
        ("BACKGROUND", (2, 1), (2, 1), PALETTE["danger_bg"]),
        ("TEXTCOLOR", (2, 1), (2, 1), PALETTE["danger_ink"]),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ]))
    story.append(cr3_table)
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("<b>Key Insight:</b> CR3 &gt; 70% is a Red Zone. Unless you have a patented form factor, stay out.", styles["Insight"]))
    story.append(PageBreak())

    # Page 3 - Mistake #2
    story.append(Paragraph("Mistake #2 — Chasing 'Average' Reviews instead of 'Median' Distribution", styles["Header"]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        "A niche with an average of 1,000 reviews might look impossible. But if the median is 50, "
        "there is a massive gap at the top held by 1-2 'dinosaurs'.",
        styles["Body"],
    ))
    story.append(Spacer(1, 0.5 * cm))
    story.append(_chart_histogram())
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("<b>Key Insight:</b> Don't fear the 'dinosaurs' (5k+ reviews). Fear a flat distribution where everyone has 500 reviews.", styles["Insight"]))
    story.append(PageBreak())

    # Page 4 - Mistake #3
    story.append(Paragraph("Mistake #3 — Overlooking Negative Feedback Patterns", styles["Header"]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        "Product quality isn't just about stars; it's about recurring pain points. "
        "Solving one 100% frequency complaint can make you the #1 Choice overnight.",
        styles["Body"],
    ))
    story.append(Spacer(1, 0.5 * cm))

    feedback_table = Table(
        [
            ["Recurring Complaint", "Frequency in 1★-3★ Reviews", "Opportunity"],
            ["Too sharp / snagging", "100%", "Redesign tip geometry + smooth finishing"],
            ["Weak adhesive", "64%", "Upgrade bonding material"],
            ["Color fades quickly", "41%", "Improve coating quality"],
        ],
        colWidths=[5 * cm, 4.2 * cm, 5.8 * cm],
    )
    feedback_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PALETTE["bg"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), PALETTE["ink"]),
        ("GRID", (0, 0), (-1, -1), 0.5, PALETTE["line"]),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (1, 1), (1, 1), PALETTE["danger_bg"]),
        ("TEXTCOLOR", (1, 1), (1, 1), PALETTE["danger_ink"]),
    ]))
    story.append(feedback_table)
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("<b>Key Insight:</b> Look for 100% frequency complaints in negative reviews. That is your product development roadmap.", styles["Insight"]))
    story.append(PageBreak())

    # Page 5 - Mistake #4
    story.append(Paragraph("Mistake #4 — Misunderstanding Price vs. Revenue Correlation", styles["Header"]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        "Higher price doesn't always mean lower volume. Sometimes, the 'Premium' gap is where "
        "the highest profit margins live, untouched by 'race-to-the-bottom' sellers.",
        styles["Body"],
    ))
    story.append(Spacer(1, 0.5 * cm))
    story.append(_chart_scatter())
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("<b>Key Insight:</b> The 'Sweet Spot' is often $2-$5 above the mass-market average if you solve a specific customer issue.", styles["Insight"]))
    story.append(PageBreak())

    # Page 6 - CTA
    story.append(Paragraph("Stop Guessing. Start Dominating.", styles["Header"]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        "Data is the only insurance policy for your Amazon launch. I provide the same level of deep-dive "
        "analysis used by 7-figure brands to vet their niches.",
        styles["Body"],
    ))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("<b>What you get in a Full Report ($500):</b>", styles["Body"]))
    for bullet in [
        "60+ Unique Product Deep-Dive.",
        "Competitor Sponsored vs. Organic Traffic Breakdown.",
        "Full Customer Feedback Loop Analysis.",
        "Raw Data Exports (CSV/XLSX) for your own research.",
        "Executive Strategic Recommendations.",
    ]:
        story.append(Paragraph(f"• {bullet}", styles["Body"]))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(
        "<b>Ready to vet your next product?</b> Reply to this message or visit [Link/Email] "
        "for a custom Niche Analysis Report.",
        styles["Insight"],
    ))

    doc.build(story)


if __name__ == "__main__":
    build_pdf()
    print("PDF generated: amazon_seller_strategy_guide.pdf")
