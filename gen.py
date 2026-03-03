#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate a 6-page premium Amazon lead-magnet PDF.
Final version with fixed text overflow in Opportunity column.
"""

from pathlib import Path
from typing import Optional, Tuple, List, Any
from dataclasses import dataclass

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    KeepTogether, Image, PageBreak, Paragraph,
    SimpleDocTemplate, Spacer, Table, TableStyle
)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass(frozen=True)
class PDFConfig:
    """PDF generation configuration."""

    # Content
    TITLE: str = "The 5 Strategy-Killing Mistakes Amazon Sellers Make in Niche Selection"
    SUBTITLE: str = "A Data-Driven Guide to Avoiding $10,000+ Launch Failures."
    OUTPUT_FILE: str = "amazon_seller_strategy_guide.pdf"

    # Corporate analytics color palette
    DEEP_BLUE: colors.Color = colors.HexColor("#1A4780")
    ALERT_RED: colors.Color = colors.HexColor("#D32F2F")
    PROFESSIONAL_GRAY: colors.Color = colors.HexColor("#F5F5F5")
    LIGHT_BLUE_BG: colors.Color = colors.HexColor("#EAF3FF")
    GRID_GRAY: colors.Color = colors.HexColor("#D7DCE2")
    TEXT_DARK: colors.Color = colors.HexColor("#1C2733")
    MUTED_GRAY: colors.Color = colors.HexColor("#6C757D")
    GOLD: colors.Color = colors.HexColor("#C9A227")

    # Layout
    MARGIN_LEFT_RIGHT: int = 50
    MARGIN_TOP_BOTTOM: int = 60

    # Logo settings
    LOGO_SCALE_FACTOR: float = 0.5
    LOGO_CANDIDATES: Tuple[str, ...] = ("icon.png", "analytics_logo.png", "logo.png")

    # Chart dimensions
    CHART_WIDTH: int = 470
    CHART_HEIGHT: int = 250


# =============================================================================
# LOGO HANDLING
# =============================================================================

class LogoManager:
    """Manages logo file operations."""

    def __init__(self, config: PDFConfig):
        self.config = config

    def find_logo_path(self) -> Optional[Path]:
        """Find existing logo file from candidates."""
        for candidate in self.config.LOGO_CANDIDATES:
            path = Path(candidate)
            if path.exists():
                return path
        return None

    def get_scaled_dimensions(self, logo_path: Path) -> Tuple[float, float]:
        """Calculate scaled logo dimensions."""
        img = ImageReader(str(logo_path))
        width, height = img.getSize()
        scale = self.config.LOGO_SCALE_FACTOR
        return width * scale, height * scale


# =============================================================================
# CHART CREATORS
# =============================================================================

class ChartCreator:
    """Creates various charts for the PDF."""

    def __init__(self, config: PDFConfig):
        self.config = config

    def create_histogram(self, width: float = 470, height: float = 250) -> Drawing:
        """Create histogram showing product maturity distribution."""
        drawing = Drawing(width, height)

        # Title
        drawing.add(String(
            8, height - 18,
            "Product Maturity Distribution",
            fontName="Helvetica-Bold", fontSize=11,
            fillColor=self.config.DEEP_BLUE
        ))

        # Create bar chart
        chart = self._create_bar_chart(width, height)
        drawing.add(chart)

        # Axis labels (adjusted to avoid overlap)
        drawing.add(String(
            225, 8, "Review Count Bins",
            fontName="Helvetica", fontSize=8,
            fillColor=self.config.MUTED_GRAY
        ))
        drawing.add(String(
            8, 126, "Products",
            fontName="Helvetica", fontSize=8,
            fillColor=self.config.MUTED_GRAY
        ))

        # Annotations
        self._add_histogram_annotations(drawing, chart)

        return drawing

    def _create_bar_chart(self, width: float, height: float) -> VerticalBarChart:
        """Create and configure bar chart."""
        chart = VerticalBarChart()
        chart.x = 55
        chart.y = 45
        chart.width = width - 95
        chart.height = height - 85

        # Data
        chart.data = [[45, 12, 7, 4, 2]]
        chart.categoryAxis.categoryNames = ["0-50", "51-200", "201-500", "501-1000", "1001+"]

        # Category axis styling (increased dy to avoid overlap)
        chart.categoryAxis.labels.fontName = "Helvetica"
        chart.categoryAxis.labels.fontSize = 7
        chart.categoryAxis.labels.dy = -15

        # Value axis styling
        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = 50
        chart.valueAxis.valueStep = 10
        chart.valueAxis.labels.fontName = "Helvetica"
        chart.valueAxis.labels.fontSize = 8
        chart.valueAxis.visibleGrid = True
        chart.valueAxis.gridStrokeColor = self.config.GRID_GRAY
        chart.valueAxis.gridStrokeWidth = 0.6

        # Bar styling
        chart.bars[0].fillColor = self.config.DEEP_BLUE
        chart.bars[0].strokeColor = colors.HexColor("#11325B")
        chart.barSpacing = 8

        return chart

    def _add_histogram_annotations(self, drawing: Drawing, chart: VerticalBarChart) -> None:
        """Add annotation elements to histogram."""
        config = self.config

        # Annotation: large low-review cluster
        x1, y1 = chart.x + 30, chart.y + 120
        drawing.add(Line(
            x1 + 90, y1 + 28, x1 + 35, y1 + 5,
            strokeColor=config.DEEP_BLUE, strokeWidth=1
        ))
        drawing.add(Polygon(
            points=[x1 + 35, y1 + 5, x1 + 41, y1 + 7, x1 + 38, y1 + 1],
            fillColor=config.DEEP_BLUE, strokeColor=config.DEEP_BLUE
        ))
        drawing.add(String(
            x1 + 92, y1 + 30, "Large low-review cluster",
            fontName="Helvetica", fontSize=8, fillColor=config.DEEP_BLUE
        ))

        # Annotation: dominant outliers
        x2, y2 = chart.x + chart.width - 55, chart.y + 30
        drawing.add(Line(
            x2 + 10, y2 + 45, x2 + 1, y2 + 18,
            strokeColor=config.ALERT_RED, strokeWidth=1
        ))
        drawing.add(Polygon(
            points=[x2 + 1, y2 + 18, x2 + 6, y2 + 20, x2 + 2, y2 + 13],
            fillColor=config.ALERT_RED, strokeColor=config.ALERT_RED
        ))
        drawing.add(String(
            x2 + 15, y2 + 47, "Dominant Outliers",
            fontName="Helvetica", fontSize=8, fillColor=config.ALERT_RED
        ))

    def create_scatter_plot(self, width: float = 470, height: float = 250) -> Drawing:
        """Create scatter plot showing price vs revenue correlation."""
        drawing = Drawing(width, height)
        config = self.config

        # Title
        drawing.add(String(
            8, height - 18, "Price vs Revenue Correlation",
            fontName="Helvetica-Bold", fontSize=11,
            fillColor=config.DEEP_BLUE
        ))

        # Plot area coordinates
        x0, y0 = 60, 45
        plot_w, plot_h = width - 105, height - 85

        # Add grid lines
        self._add_grid_lines(drawing, x0, y0, plot_w, plot_h, config)

        # Add axes
        drawing.add(Line(
            x0, y0, x0 + plot_w, y0,
            strokeColor=config.TEXT_DARK, strokeWidth=1.1
        ))
        drawing.add(Line(
            x0, y0, x0, y0 + plot_h,
            strokeColor=config.TEXT_DARK, strokeWidth=1.1
        ))

        # Axis labels
        drawing.add(String(
            x0 + plot_w / 2 - 22, 15, "Price ($)",
            fontName="Helvetica", fontSize=8,
            fillColor=config.MUTED_GRAY
        ))
        drawing.add(String(
            5, y0 + plot_h / 2, "Monthly Revenue ($)",
            fontName="Helvetica", fontSize=8,
            fillColor=config.MUTED_GRAY
        ))

        # Data points
        self._add_scatter_points(drawing, x0, y0, plot_w, plot_h, config)

        return drawing

    def _add_grid_lines(self, drawing: Drawing, x0: float, y0: float,
                        plot_w: float, plot_h: float, config: PDFConfig) -> None:
        """Add grid lines to scatter plot."""
        for i in range(6):
            y = y0 + (plot_h / 5) * i
            drawing.add(Line(
                x0, y, x0 + plot_w, y,
                strokeColor=config.GRID_GRAY, strokeWidth=0.7
            ))

        for j in range(6):
            x = x0 + (plot_w / 5) * j
            drawing.add(Line(
                x, y0, x, y0 + plot_h,
                strokeColor=config.GRID_GRAY, strokeWidth=0.7
            ))

    def _add_scatter_points(self, drawing: Drawing, x0: float, y0: float,
                           plot_w: float, plot_h: float, config: PDFConfig) -> None:
        """Add data points and annotations to scatter plot."""
        # Sample data
        prices = [12, 14, 16, 18, 21, 24, 27, 31, 34, 37, 41, 46]
        revenues = [9000, 11000, 12500, 13000, 14500, 17000, 18500, 21000, 26500, 31500, 29000, 24500]

        # Scale functions
        min_p, max_p = 10, 50
        min_r, max_r = 8000, 33000

        def scale_x(p: float) -> float:
            return x0 + ((p - min_p) / (max_p - min_p)) * plot_w

        def scale_y(r: float) -> float:
            return y0 + ((r - min_r) / (max_r - min_r)) * plot_h

        # Plot points
        for price, revenue in zip(prices, revenues):
            color = self._get_price_color(price, config)
            drawing.add(Circle(
                scale_x(price), scale_y(revenue), 4,
                fillColor=color, strokeColor=colors.white, strokeWidth=0.5
            ))

        # Add sweet spot annotation
        sweet_x, sweet_y = scale_x(37), scale_y(31500)
        drawing.add(Circle(
            sweet_x, sweet_y, 5.2,
            fillColor=config.ALERT_RED,
            strokeColor=colors.HexColor("#8E2020"),
            strokeWidth=0.7
        ))
        drawing.add(Line(
            sweet_x + 6, sweet_y + 4, sweet_x + 86, sweet_y + 30,
            strokeColor=config.ALERT_RED, strokeWidth=1
        ))
        drawing.add(String(
            sweet_x + 88, sweet_y + 31, "The Profit Sweet Spot",
            fontName="Helvetica", fontSize=8, fillColor=config.ALERT_RED
        ))

    def _get_price_color(self, price: float, config: PDFConfig) -> colors.Color:
        """Get color for price point."""
        if price <= 20:
            return colors.HexColor("#0D2E57")
        elif price <= 30:
            return config.DEEP_BLUE
        elif price <= 40:
            return colors.HexColor("#3A6EA5")
        else:
            return config.GOLD


# =============================================================================
# STYLES MANAGER
# =============================================================================

class StyleManager:
    """Manages paragraph styles for the PDF."""

    def __init__(self, config: PDFConfig):
        self.config = config
        self.styles = getSampleStyleSheet()
        self._add_custom_styles()

    def _add_custom_styles(self) -> None:
        """Add custom paragraph styles."""
        config = self.config

        self.styles.add(ParagraphStyle(
            name="cover_title",
            fontName="Helvetica-Bold", fontSize=28, leading=33,
            textColor=config.DEEP_BLUE, alignment=1
        ))
        self.styles.add(ParagraphStyle(
            name="cover_sub",
            fontName="Helvetica", fontSize=16, leading=21,
            textColor=config.MUTED_GRAY, alignment=1
        ))
        self.styles.add(ParagraphStyle(
            name="cover_footer",
            fontName="Helvetica", fontSize=10, leading=13,
            textColor=config.MUTED_GRAY, alignment=1
        ))
        self.styles.add(ParagraphStyle(
            name="header",
            fontName="Helvetica-Bold", fontSize=18, leading=22,
            textColor=config.DEEP_BLUE
        ))
        self.styles.add(ParagraphStyle(
            name="body",
            fontName="Helvetica", fontSize=11, leading=16,
            textColor=config.TEXT_DARK
        ))
        self.styles.add(ParagraphStyle(
            name="insight",
            fontName="Helvetica-Bold", fontSize=10.5, leading=15,
            textColor=config.DEEP_BLUE
        ))
        self.styles.add(ParagraphStyle(
            name="cta",
            fontName="Helvetica-Bold", fontSize=16, leading=22,
            textColor=config.DEEP_BLUE, alignment=1
        ))

    def get(self, style_name: str) -> ParagraphStyle:
        """Get style by name."""
        return self.styles[style_name]

    def get_all(self):
        """Get all styles."""
        return self.styles


# =============================================================================
# TABLE CREATORS
# =============================================================================

class TableCreator:
    """Creates various tables for the PDF."""

    def __init__(self, config: PDFConfig, styles: StyleManager):
        self.config = config
        self.styles = styles

    def create_insight_box(self, text: str, width: float) -> Table:
        """Create styled insight box."""
        table = Table(
            [[Paragraph(text, self.styles.get("insight"))]],
            colWidths=[width]
        )

        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), self.config.LIGHT_BLUE_BG),
            ("BOX", (0, 0), (0, 0), 1, self.config.DEEP_BLUE),
            ("LEFTPADDING", (0, 0), (0, 0), 10),
            ("RIGHTPADDING", (0, 0), (0, 0), 10),
            ("TOPPADDING", (0, 0), (0, 0), 8),
            ("BOTTOMPADDING", (0, 0), (0, 0), 8),
        ]))

        return table

    def create_cr3_table(self, content_width: float) -> Table:
        """Create CR3 risk assessment table."""
        data = [
            ["Metric", "Value", "Risk Level"],
            ["CR3 (Top 3 Brand Share)", "82%", "High Risk"]
        ]

        col_widths = [
            content_width * 0.52,
            content_width * 0.18,
            content_width * 0.30
        ]

        table = Table(data, colWidths=col_widths)

        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BACKGROUND", (0, 0), (-1, 0), self.config.PROFESSIONAL_GRAY),
            ("GRID", (0, 0), (-1, -1), 0.8, colors.HexColor("#D0D0D0")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (1, 1), (1, 1), colors.HexColor("#FFD9D9")),
            ("TEXTCOLOR", (1, 1), (1, 1), self.config.ALERT_RED),
        ]))

        return table

    def create_feedback_table(self, content_width: float) -> Table:
        """Create customer feedback analysis table with proper text wrapping."""
        # Define custom styles for cells
        body_style = self.styles.get("body")
        header_style = ParagraphStyle(
            "feedback_header",
            parent=body_style,
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=self.config.TEXT_DARK
        )
        red_bold_style = ParagraphStyle(
            "red_bold",
            parent=body_style,
            textColor=self.config.ALERT_RED,
            fontName="Helvetica-Bold",
            fontSize=10
        )
        opportunity_style = ParagraphStyle(
            "opportunity",
            parent=body_style,
            fontSize=9,          # Smaller font to ensure fitting
            leading=12,
            textColor=self.config.TEXT_DARK
        )

        # Prepare data with Paragraphs for proper wrapping
        data = [
            [
                Paragraph("Recurring Complaint", header_style),
                Paragraph("Frequency", header_style),
                Paragraph("Opportunity", header_style)
            ],
            [
                Paragraph("Too sharp / snagging", body_style),
                Paragraph("100%", red_bold_style),
                Paragraph("Redesign tip geometry and smooth finishing process", opportunity_style)
            ],
            [
                Paragraph("Weak adhesive", body_style),
                Paragraph("64%", body_style),
                Paragraph("Upgrade bonding material and pre-use preparation guide", opportunity_style)
            ],
            [
                Paragraph("Color fades quickly", body_style),
                Paragraph("41%", body_style),
                Paragraph("Higher-grade coating + packaging protection", opportunity_style)
            ],
        ]

        # Adjusted column widths: 35%, 20%, 45% (more space for Opportunity)
        col_widths = [
            content_width * 0.35,
            content_width * 0.20,
            content_width * 0.45
        ]

        table = Table(data, colWidths=col_widths)

        # Apply table styling (grid, background, etc.) – text colors are handled by Paragraph styles
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), self.config.PROFESSIONAL_GRAY),
            ("GRID", (0, 0), (-1, -1), 0.8, colors.HexColor("#D0D0D0")),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))

        return table

    def create_premium_offer_box(self, content_width: float) -> Table:
        """
        Create a visually highlighted box for the premium offer.
        Includes header, bullet list with checkmarks, and prominent price.
        """
        # Define styles for elements inside the box
        header_style = ParagraphStyle(
            "offer_header",
            parent=self.styles.get("body"),
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            textColor=self.config.DEEP_BLUE
        )
        bullet_style = ParagraphStyle(
            "offer_bullet",
            parent=self.styles.get("body"),
            fontSize=10,
            leading=14,
            leftIndent=10,
            textColor=self.config.TEXT_DARK
        )

        # Build content rows
        content_rows = [
            [Paragraph("What you get in a Full Report <i>(Investment: $500)</i>:", header_style)],
            [Spacer(1, 6)],
            [Paragraph("✔ 60+ Unique Product Deep-Dive", bullet_style)],
            [Paragraph("✔ Competitor Sponsored vs. Organic Traffic Breakdown", bullet_style)],
            [Paragraph("✔ Full Customer Feedback Loop Analysis", bullet_style)],
            [Paragraph("✔ Raw Data Exports (CSV/XLSX) for your own research", bullet_style)],
            [Paragraph("✔ Executive Strategic Recommendations", bullet_style)],
            [Spacer(1, 6)],
        ]

        # Create table with one column
        table = Table(content_rows, colWidths=[content_width - 20])  # inner padding

        # Apply overall box styling
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF8E8")),  # light cream background
            ("BOX", (0, 0), (-1, -1), 1, self.config.DEEP_BLUE),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))

        return table


# =============================================================================
# PDF BUILDER
# =============================================================================

class PDFBuilder:
    """Main PDF builder class."""

    def __init__(self, config: Optional[PDFConfig] = None):
        self.config = config or PDFConfig()
        self.styles = StyleManager(self.config)
        self.logo_manager = LogoManager(self.config)
        self.chart_creator = ChartCreator(self.config)
        self.table_creator = TableCreator(self.config, self.styles)

        self.content_width = A4[0] - 2 * self.config.MARGIN_LEFT_RIGHT
        self.story: List[Any] = []

    def build(self, output_file: Optional[str] = None,
              company_name: str = "Your Company Name") -> None:
        """Build the complete PDF."""
        output_file = output_file or self.config.OUTPUT_FILE

        doc = SimpleDocTemplate(
            output_file,
            pagesize=A4,
            leftMargin=self.config.MARGIN_LEFT_RIGHT,
            rightMargin=self.config.MARGIN_LEFT_RIGHT,
            topMargin=self.config.MARGIN_TOP_BOTTOM,
            bottomMargin=self.config.MARGIN_TOP_BOTTOM,
            title=self.config.TITLE,
            author=company_name,
        )

        self._build_all_pages(company_name)
        doc.build(self.story)
        print(f"PDF generated: {output_file}")

    def _build_all_pages(self, company_name: str) -> None:
        """Build all pages of the PDF."""
        self._build_cover_page(company_name)
        self._build_mistake_pages()

    def _build_cover_page(self, company_name: str) -> None:
        """Build cover page."""
        cover = []

        logo_path = self.logo_manager.find_logo_path()
        if logo_path:
            w, h = self.logo_manager.get_scaled_dimensions(logo_path)
            cover.append(Image(str(logo_path), width=w, height=h, hAlign="CENTER"))
        else:
            cover.append(Paragraph("Analytics", self.styles.get("header")))

        cover.append(Spacer(1, 40))
        cover.append(Paragraph(self.config.TITLE, self.styles.get("cover_title")))
        cover.append(Spacer(1, 18))
        cover.append(Paragraph(self.config.SUBTITLE, self.styles.get("cover_sub")))
        cover.append(Spacer(1, 310))
        cover.append(Paragraph(
            f"Free Strategy Insights | {company_name}",
            self.styles.get("cover_footer")
        ))

        self.story.append(KeepTogether(cover))
        self.story.append(PageBreak())

    def _build_mistake_pages(self) -> None:
        """Build all mistake pages."""
        self._build_mistake_1_page()
        self._build_mistake_2_page()
        self._build_mistake_3_page()
        self._build_mistake_4_page()
        self._build_cta_page()

    def _build_mistake_1_page(self) -> None:
        """Build page for Mistake #1."""
        content = [
            Paragraph(
                "Mistake #1 — Ignoring the Saturation Index (CR3)",
                self.styles.get("header")
            ),
            Spacer(1, 10),
            Paragraph(
                "Many sellers look at high total revenue but ignore who controls it. "
                "If the Top 3 brands control &gt;70% (CR3), you are fighting for crumbs.",
                self.styles.get("body")
            ),
            Spacer(1, 14),
            self.table_creator.create_cr3_table(self.content_width),
            Spacer(1, 14),
            self.table_creator.create_insight_box(
                "Key Insight: CR3 > 70% is a Red Zone. "
                "Unless you have a patented form factor, stay out.",
                self.content_width
            )
        ]

        self.story.append(KeepTogether(content))
        self.story.append(PageBreak())

    def _build_mistake_2_page(self) -> None:
        """Build page for Mistake #2."""
        content = [
            Paragraph(
                "Mistake #2 — Chasing 'Average' Reviews instead of 'Median'",
                self.styles.get("header")
            ),
            Spacer(1, 10),
            Paragraph(
                "A niche with an average of 1,000 reviews might look impossible. "
                "But if the median is 50, there is often a concentrated gap where "
                "only 1-2 dominant outliers skew the mean.",
                self.styles.get("body")
            ),
            Spacer(1, 14),
            self.chart_creator.create_histogram(
                width=self.content_width,
                height=self.config.CHART_HEIGHT
            ),
            Spacer(1, 12),
            Paragraph(
                "<b>Key Insight:</b> Don't fear the 'dinosaurs' (5k+ reviews). "
                "Fear a flat distribution.",
                self.styles.get("insight")
            ),
        ]

        self.story.append(KeepTogether(content))
        self.story.append(PageBreak())

    def _build_mistake_3_page(self) -> None:
        """Build page for Mistake #3."""
        content = [
            Paragraph(
                "Mistake #3 — Overlooking Recurring Pain Points",
                self.styles.get("header")
            ),
            Spacer(1, 10),
            Paragraph(
                "Product quality isn't just about star rating averages. "
                "Winning sellers diagnose recurring pain points and systematically "
                "remove the exact friction buyers repeatedly mention.",
                self.styles.get("body")
            ),
            Spacer(1, 14),
            self.table_creator.create_feedback_table(self.content_width),
            Spacer(1, 12),
            Paragraph(
                "<b>Key Insight:</b> Look for 100% frequency complaints in negative "
                "reviews; that is your product development roadmap.",
                self.styles.get("insight")
            ),
        ]

        self.story.append(KeepTogether(content))
        self.story.append(PageBreak())

    def _build_mistake_4_page(self) -> None:
        """Build page for Mistake #4."""
        content = [
            Paragraph(
                "Mistake #4 — Misunderstanding the 'Premium Gap'",
                self.styles.get("header")
            ),
            Spacer(1, 10),
            Paragraph(
                "Higher price does not automatically mean lower demand. "
                "In many niches, the strongest margin opportunity appears when "
                "product differentiation justifies a moderate premium.",
                self.styles.get("body")
            ),
            Spacer(1, 14),
            self.chart_creator.create_scatter_plot(
                width=self.content_width,
                height=self.config.CHART_HEIGHT
            ),
            Spacer(1, 12),
            Paragraph(
                "<b>Key Insight:</b> The sweet spot is frequently $2-$5 above "
                "mass-market pricing when a specific customer pain is solved.",
                self.styles.get("insight")
            ),
        ]

        self.story.append(KeepTogether(content))
        self.story.append(PageBreak())

    def _build_cta_page(self) -> None:
        """Build Call-to-Action page."""
        content = [
            Paragraph("Stop Guessing. Start Dominating.", self.styles.get("header")),
            Spacer(1, 10),
            Paragraph(
                "Data is the only insurance policy for your Amazon launch. "
                "I provide the same level of deep-dive analysis used by 7-figure brands "
                "to vet their niches.",
                self.styles.get("body")
            ),
            Spacer(1, 20),
            self.table_creator.create_premium_offer_box(self.content_width),
            Spacer(1, 25),
            Paragraph(
                "Ready to vet your next product? Reply to this message for a "
                "Custom Niche Analysis.",
                self.styles.get("cta")
            ),
        ]

        self.story.append(KeepTogether(content))


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    """Main entry point."""
    builder = PDFBuilder()
    builder.build(company_name="CR3 Analytics")


if __name__ == "__main__":
    main()