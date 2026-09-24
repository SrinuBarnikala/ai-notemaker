"""
PDF Generation Engine for Living Structured Notes.

Generates clean, publication-ready, beautifully formatted PDF documents
derived directly from canonical structured NoteResponse data.

Preserves the principle:
"The source should remain: Structured Note.
PDF is generated from the note.
Never make PDF the canonical representation."
"""

import io
import re
import html
from typing import Optional, List, Dict, Any

from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Preformatted,
    HRFlowable,
    KeepTogether,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY

from backend.app.schemas.note import NoteResponse, NoteSectionData, NoteBlock


# ==============================================================================
# COLOR PALETTE
# ==============================================================================
PRIMARY_COLOR = colors.HexColor("#1E1B4B")      # Deep Indigo / Navy 950
SECONDARY_COLOR = colors.HexColor("#4338CA")    # Indigo 700
ACCENT_COLOR = colors.HexColor("#4F46E5")       # Indigo 600
ACCENT_LIGHT = colors.HexColor("#EEF2FF")       # Indigo 50
TEXT_DARK = colors.HexColor("#0F172A")          # Slate 900
TEXT_BODY = colors.HexColor("#1E293B")          # Slate 800
TEXT_MUTED = colors.HexColor("#64748B")         # Slate 500
BORDER_LIGHT = colors.HexColor("#E2E8F0")       # Slate 200
BORDER_DARK = colors.HexColor("#334155")        # Slate 700

# Callout Colors
DEF_BORDER = colors.HexColor("#D97706")         # Amber 600
DEF_BG = colors.HexColor("#FFFBEB")             # Amber 50
WARN_BORDER = colors.HexColor("#E11D48")        # Rose 600
WARN_BG = colors.HexColor("#FFF1F2")            # Rose 50
EX_BORDER = colors.HexColor("#059669")          # Emerald 600
EX_BG = colors.HexColor("#F0FDF4")              # Emerald 50
DIAG_BORDER = colors.HexColor("#0284C7")        # Sky 600
DIAG_BG = colors.HexColor("#F0F9FF")            # Sky 50

# Code Colors
CODE_BG = colors.HexColor("#0F172A")            # Slate 900
CODE_HEADER_BG = colors.HexColor("#1E293B")     # Slate 800
CODE_TEXT = colors.HexColor("#F8FAFC")          # Slate 50
CODE_BORDER = colors.HexColor("#334155")        # Slate 700


# ==============================================================================
# RUNNING NUMBERED CANVAS (HEADERS & FOOTERS)
# ==============================================================================
class NotePDFCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and render total page count
    along with running headers and publication footers.
    """
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: List[Dict[str, Any]] = []
        self.doc_topic: str = "Living Technical Note"
        self.doc_version: int = 1

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_header_footer(num_pages)
            super().showPage()
        super().save()

    def draw_header_footer(self, total_pages: int) -> None:
        self.saveState()
        page_w, page_h = letter
        margin = 43.2

        # Running Top Header on Page 2+
        if self._pageNumber > 1:
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(SECONDARY_COLOR)
            topic_str = self.doc_topic
            if len(topic_str) > 65:
                topic_str = topic_str[:62] + "..."
            self.drawString(margin, page_h - 32, topic_str.upper())

            self.setFont("Helvetica", 8)
            self.setFillColor(TEXT_MUTED)
            v_str = f"Living Note • v{self.doc_version}"
            self.drawRightString(page_w - margin, page_h - 32, v_str)

            self.setStrokeColor(BORDER_LIGHT)
            self.setLineWidth(0.5)
            self.line(margin, page_h - 38, page_w - margin, page_h - 38)

        # Running Bottom Footer on all pages
        self.setStrokeColor(BORDER_LIGHT)
        self.setLineWidth(0.5)
        self.line(margin, 40, page_w - margin, 40)

        self.setFont("Helvetica", 7.5)
        self.setFillColor(TEXT_MUTED)
        self.drawString(margin, 26, "Personalized Technical Note Maker • Living Structured Document")

        page_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(page_w - margin, 26, page_str)
        self.restoreState()


def _create_canvas_factory(topic: str, version: int):
    """
    Factory creating a NotePDFCanvas instance pre-bound to topic & version metadata.
    """
    class BoundNotePDFCanvas(NotePDFCanvas):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.doc_topic = topic
            self.doc_version = version

    return BoundNotePDFCanvas


# ==============================================================================
# TEXT FORMATTING & MARKDOWN TRANSLATION
# ==============================================================================
def clean_markdown_for_paragraph(text: Optional[str]) -> str:
    """
    Escapes raw XML entities and translates common inline Markdown syntax
    (**bold**, *italic*, `code`) into ReportLab Paragraph XML tags.
    """
    if not text:
        return ""

    # 1. Escape XML characters
    s = html.escape(str(text))

    # 2. Bold: **text** -> <b>text</b>
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)

    # 3. Italic: *text* or _text_ -> <i>text</i>
    s = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", s)

    # 4. Inline code: `text` -> Courier font with accent color
    s = re.sub(
        r"`([^`]+?)`",
        r'<font face="Courier-Bold" color="#0369A1">\1</font>',
        s,
    )

    # 5. Newlines to HTML line breaks
    s = s.replace("\r\n", "<br/>").replace("\n", "<br/>")

    return s


def wrap_preformatted(text: Optional[str], max_chars: int = 76) -> str:
    """
    Ensures preformatted text (code/diagrams) does not overflow the right margin
    by soft-wrapping lines longer than max_chars.
    """
    if not text:
        return ""

    wrapped_lines: List[str] = []
    for line in str(text).splitlines():
        if len(line) <= max_chars:
            wrapped_lines.append(line)
        else:
            # Chunk long lines
            chunks = [line[i:i + max_chars] for i in range(0, len(line), max_chars)]
            wrapped_lines.extend(chunks)

    return "\n".join(wrapped_lines)


# ==============================================================================
# STYLESHEET SETUP
# ==============================================================================
def get_pdf_styles():
    """
    Returns a unified, tailored stylesheet for the technical note layout.
    """
    styles = getSampleStyleSheet()

    # Document Main Title
    styles.add(ParagraphStyle(
        name="DocTitle",
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=PRIMARY_COLOR,
        spaceAfter=6,
    ))

    # Document Subtitle / Version Pill
    styles.add(ParagraphStyle(
        name="DocVersionMeta",
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=ACCENT_COLOR,
        spaceAfter=12,
    ))

    # Summary Callout Text
    styles.add(ParagraphStyle(
        name="DocSummaryText",
        fontName="Helvetica",
        fontSize=10,
        leading=15,
        textColor=TEXT_BODY,
    ))

    # Summary Label
    styles.add(ParagraphStyle(
        name="DocSummaryLabel",
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=13,
        textColor=ACCENT_COLOR,
        spaceAfter=4,
    ))

    # Section Heading (H2)
    styles.add(ParagraphStyle(
        name="SectionHeading",
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        textColor=PRIMARY_COLOR,
        spaceBefore=14,
        spaceAfter=2,
        keepWithNext=True,
    ))

    # Section Sub-meta (Depth & Type)
    styles.add(ParagraphStyle(
        name="SectionSubMeta",
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=TEXT_MUTED,
        spaceAfter=8,
        keepWithNext=True,
    ))

    # Body Paragraph
    styles.add(ParagraphStyle(
        name="NoteBody",
        fontName="Helvetica",
        fontSize=9.5,
        leading=14.5,
        textColor=TEXT_BODY,
        spaceAfter=7,
        alignment=TA_JUSTIFY,
    ))

    # Callout Content
    styles.add(ParagraphStyle(
        name="CalloutContent",
        fontName="Helvetica",
        fontSize=9,
        leading=13.5,
        textColor=TEXT_BODY,
    ))

    # Code Header Left
    styles.add(ParagraphStyle(
        name="CodeHeaderLeft",
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#F8FAFC"),
    ))

    # Code Header Right (Complexity Badge)
    styles.add(ParagraphStyle(
        name="CodeHeaderRight",
        fontName="Courier-Bold",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#38BDF8"),
        alignment=TA_RIGHT,
    ))

    # Code Preformatted Body
    styles.add(ParagraphStyle(
        name="CodePreformatted",
        fontName="Courier",
        fontSize=7.5,
        leading=10.5,
        textColor=CODE_TEXT,
    ))

    # Diagram Preformatted Body
    styles.add(ParagraphStyle(
        name="DiagramPreformatted",
        fontName="Courier",
        fontSize=7.5,
        leading=10.5,
        textColor=TEXT_DARK,
    ))

    # Caption / Footnote
    styles.add(ParagraphStyle(
        name="NoteCaption",
        fontName="Helvetica-Oblique",
        fontSize=8,
        leading=11,
        textColor=TEXT_MUTED,
        alignment=TA_CENTER,
        spaceAfter=8,
    ))

    # Table Cell Normal
    styles.add(ParagraphStyle(
        name="TableCellText",
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=TEXT_BODY,
    ))

    # Table Cell Header
    styles.add(ParagraphStyle(
        name="TableCellHeader",
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=12,
        textColor=colors.white,
    ))

    return styles


# ==============================================================================
# FLOWABLE GENERATORS FOR STRUCTURED BLOCKS
# ==============================================================================
USABLE_WIDTH = 525.6  # 612 - 2 * 43.2 pt


def _render_definition_block(block: NoteBlock, styles) -> KeepTogether:
    term_text = block.term or "Definition"
    content_html = f"<b>📖 {clean_markdown_for_paragraph(term_text)}</b><br/>{clean_markdown_for_paragraph(block.content)}"
    p = Paragraph(content_html, styles["CalloutContent"])

    t = Table([[p]], colWidths=[USABLE_WIDTH])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), DEF_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#FDE68A")),
        ("LINELEFT", (0, 0), (0, -1), 3.5, DEF_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return KeepTogether([t, Spacer(1, 8)])


def _render_warning_block(block: NoteBlock, styles) -> KeepTogether:
    title_text = block.title or "Warning / Pitfall"
    content_html = f"<b>⚠️ {clean_markdown_for_paragraph(title_text)}</b><br/>{clean_markdown_for_paragraph(block.content)}"
    p = Paragraph(content_html, styles["CalloutContent"])

    t = Table([[p]], colWidths=[USABLE_WIDTH])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WARN_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#FECDD3")),
        ("LINELEFT", (0, 0), (0, -1), 3.5, WARN_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return KeepTogether([t, Spacer(1, 8)])


def _render_example_block(block: NoteBlock, styles) -> KeepTogether:
    title_text = block.title or "Practical Example"
    content_html = f"<b>💡 EXAMPLE: {clean_markdown_for_paragraph(title_text)}</b><br/>{clean_markdown_for_paragraph(block.content)}"
    p = Paragraph(content_html, styles["CalloutContent"])

    t = Table([[p]], colWidths=[USABLE_WIDTH])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), EX_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#A7F3D0")),
        ("LINELEFT", (0, 0), (0, -1), 3.5, EX_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return KeepTogether([t, Spacer(1, 8)])


def _render_code_block(block: NoteBlock, styles) -> KeepTogether:
    flowables = []
    lang_str = (block.language or "CODE").upper()
    title_str = block.title or f"{lang_str} Implementation"
    left_p = Paragraph(f"💻 <b>{clean_markdown_for_paragraph(title_str)}</b>", styles["CodeHeaderLeft"])

    right_text = ""
    if block.complexity:
        right_text = f"Complexity: {clean_markdown_for_paragraph(block.complexity)}"
    right_p = Paragraph(right_text, styles["CodeHeaderRight"])

    # Header bar
    header_table = Table([[left_p, right_p]], colWidths=[USABLE_WIDTH * 0.65, USABLE_WIDTH * 0.35])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CODE_HEADER_BG),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    flowables.append(header_table)

    # Code body
    raw_code = block.code or block.content or ""
    wrapped_code = wrap_preformatted(raw_code, max_chars=78)
    pre = Preformatted(wrapped_code, styles["CodePreformatted"])

    code_table = Table([[pre]], colWidths=[USABLE_WIDTH])
    code_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, CODE_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    flowables.append(code_table)

    # Expected output if available
    if block.expected_output:
        out_html = f"<b>Output:</b> <font face='Courier'>{clean_markdown_for_paragraph(block.expected_output)}</font>"
        out_p = Paragraph(out_html, styles["CalloutContent"])
        out_table = Table([[out_p]], colWidths=[USABLE_WIDTH])
        out_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
            ("LINELEFT", (0, 0), (0, -1), 2.5, colors.HexColor("#64748B")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        flowables.append(out_table)

    flowables.append(Spacer(1, 8))
    return KeepTogether(flowables)


def _render_diagram_block(block: NoteBlock, styles) -> KeepTogether:
    flowables = []
    title_str = block.title or "Architecture Diagram"
    type_badge = (block.diagram_type or "Diagram").upper()
    left_p = Paragraph(f"📊 <b>{clean_markdown_for_paragraph(title_str)}</b>", styles["CodeHeaderLeft"])
    right_p = Paragraph(f"<b>{type_badge}</b>", styles["CodeHeaderRight"])

    # Header bar
    header_table = Table([[left_p, right_p]], colWidths=[USABLE_WIDTH * 0.75, USABLE_WIDTH * 0.25])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0284C7")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    flowables.append(header_table)

    # Optional visual description
    if block.visual_description:
        desc_p = Paragraph(f"<i>Flow: {clean_markdown_for_paragraph(block.visual_description)}</i>", styles["CalloutContent"])
        desc_table = Table([[desc_p]], colWidths=[USABLE_WIDTH])
        desc_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), DIAG_BG),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        flowables.append(desc_table)

    # Diagram spec (Mermaid / ASCII representation)
    spec_text = block.diagram_spec or block.content or ""
    wrapped_spec = wrap_preformatted(spec_text, max_chars=78)
    pre = Preformatted(wrapped_spec, styles["DiagramPreformatted"])

    spec_table = Table([[pre]], colWidths=[USABLE_WIDTH])
    spec_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    flowables.append(spec_table)

    # Caption if available
    if block.caption:
        flowables.append(Spacer(1, 2))
        flowables.append(Paragraph(f"Figure: {clean_markdown_for_paragraph(block.caption)}", styles["NoteCaption"]))

    flowables.append(Spacer(1, 8))
    return KeepTogether(flowables)


def _render_comparison_block(block: NoteBlock, styles) -> KeepTogether:
    flowables = []
    if block.title:
        title_p = Paragraph(f"<b>⚖️ {clean_markdown_for_paragraph(block.title)}</b>", styles["SectionHeading"])
        flowables.append(title_p)

    if block.content:
        content_p = Paragraph(clean_markdown_for_paragraph(block.content), styles["NoteBody"])
        flowables.append(content_p)

    # Render structured comparison items as a table
    if block.items and len(block.items) > 0:
        keys = list(block.items[0].keys())
        col_w = USABLE_WIDTH / max(len(keys), 1)

        table_data = []
        # Header row
        header_cells = [
            Paragraph(f"<b>{clean_markdown_for_paragraph(k.replace('_', ' ').title())}</b>", styles["TableCellHeader"])
            for k in keys
        ]
        table_data.append(header_cells)

        # Data rows
        for item in block.items:
            row_cells = [
                Paragraph(clean_markdown_for_paragraph(str(item.get(k, ""))), styles["TableCellText"])
                for k in keys
            ]
            table_data.append(row_cells)

        comp_table = Table(table_data, colWidths=[col_w] * len(keys))
        comp_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]
        for row_idx in range(1, len(table_data)):
            if row_idx % 2 == 0:
                comp_style.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#F8FAFC")))
            else:
                comp_style.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.white))

        comp_table.setStyle(TableStyle(comp_style))
        flowables.append(comp_table)

    flowables.append(Spacer(1, 8))
    return KeepTogether(flowables)


# ==============================================================================
# MAIN EXPORT ENTRYPOINT
# ==============================================================================
def generate_note_pdf(note_data: NoteResponse) -> bytes:
    """
    Synthesizes a publication-quality PDF from a structured NoteResponse.

    Strict adherence:
    - Never replaces structured note as source of truth.
    - PDF is derived dynamically from note blocks.
    - Preserves clean layout, headers, footers, code syntax blocks,
      diagram specifications, definitions, warnings, and TOC.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=43.2,
        rightMargin=43.2,
        topMargin=46,
        bottomMargin=46,
    )

    styles = get_pdf_styles()
    story = []

    # 1. Document Title & Topic Banner
    title_p = Paragraph(clean_markdown_for_paragraph(note_data.topic), styles["DocTitle"])
    story.append(title_p)

    # Version & Date Meta Bar
    created_str = note_data.created_at.strftime("%b %d, %Y")
    updated_str = note_data.updated_at.strftime("%b %d, %Y")
    meta_html = (
        f"<b>LIVING NOTE VERSION {note_data.version}</b> &bull; "
        f"Updated: {updated_str} &bull; "
        f"{len(note_data.sections)} Structured Sections"
    )
    story.append(Paragraph(meta_html, styles["DocVersionMeta"]))

    # Summary Callout Box
    summary_label = Paragraph("<b>PERSONALIZED SUMMARY FOR LEARNER</b>", styles["DocSummaryLabel"])
    summary_text = Paragraph(clean_markdown_for_paragraph(note_data.summary), styles["DocSummaryText"])
    summary_table = Table([[summary_label], [summary_text]], colWidths=[USABLE_WIDTH])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("LINELEFT", (0, 0), (0, -1), 3.5, ACCENT_COLOR),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(summary_table)

    # Evolution notice if revisions exist
    if note_data.revisions:
        rev_count = len(note_data.revisions)
        rev_notice = Paragraph(
            f"<i>Living Note Evolution: v{note_data.version} reflects {rev_count} personalized revision cycles.</i>",
            styles["NoteCaption"],
        )
        story.append(Spacer(1, 4))
        story.append(rev_notice)

    story.append(Spacer(1, 10))

    # 2. Table of Contents
    story.append(Paragraph("<b>Table of Contents</b>", styles["SectionSubMeta"]))
    toc_data = []
    for s in note_data.sections:
        s_title_p = Paragraph(f"<b>{s.order_index}.</b> {clean_markdown_for_paragraph(s.title)}", styles["TableCellText"])
        s_depth_p = Paragraph(f"<i>{s.depth.title()}</i>", styles["TableCellText"])
        s_type_p = Paragraph(f"{s.section_type.replace('_', ' ').title()}", styles["TableCellText"])
        toc_data.append([s_title_p, s_depth_p, s_type_p])

    if toc_data:
        toc_table = Table(toc_data, colWidths=[USABLE_WIDTH * 0.65, USABLE_WIDTH * 0.17, USABLE_WIDTH * 0.18])
        toc_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FAFAFA")),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#F1F5F9")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(toc_table)

    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=1, color=BORDER_LIGHT, spaceAfter=10))

    # 3. Sections Content
    for section in note_data.sections:
        # Section Header
        sec_title = f"{section.order_index}. {clean_markdown_for_paragraph(section.title)}"
        story.append(Paragraph(sec_title, styles["SectionHeading"]))

        # Section Meta
        meta_str = f"Depth: <b>{section.depth.title()}</b>  &bull;  Type: <b>{section.section_type.replace('_', ' ').title()}</b>"
        story.append(Paragraph(meta_str, styles["SectionSubMeta"]))
        story.append(Spacer(1, 4))

        # Blocks
        for block in section.blocks:
            if block.type == "paragraph":
                p_text = clean_markdown_for_paragraph(block.content)
                story.append(Paragraph(p_text, styles["NoteBody"]))
            elif block.type == "definition":
                story.append(_render_definition_block(block, styles))
            elif block.type == "warning":
                story.append(_render_warning_block(block, styles))
            elif block.type == "example":
                story.append(_render_example_block(block, styles))
            elif block.type == "code":
                story.append(_render_code_block(block, styles))
            elif block.type == "diagram":
                story.append(_render_diagram_block(block, styles))
            elif block.type == "comparison":
                story.append(_render_comparison_block(block, styles))
            else:
                p_text = clean_markdown_for_paragraph(block.content)
                story.append(Paragraph(p_text, styles["NoteBody"]))

        story.append(Spacer(1, 8))

    # 4. Closing Note
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E1"), spaceBefore=10, spaceAfter=8))
    closing_p = Paragraph(
        "<i>Living note created and maintained by Personalized Technical Note Maker. Source of truth: Structured Note.</i>",
        styles["NoteCaption"],
    )
    story.append(closing_p)

    # Build document with custom canvas
    canvas_factory = _create_canvas_factory(note_data.topic, note_data.version)
    doc.build(story, canvasmaker=canvas_factory)

    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
