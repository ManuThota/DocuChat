"""
backend/services/export_service.py — Export chat history as a PDF.

Uses ReportLab to generate a formatted PDF document containing:
  - Header with DocuChat branding
  - Chat title and export date
  - All messages styled by role (user vs assistant)
"""

from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, HRFlowable

# ─── Color palette ───────────────────────────────────────────────────────────
PURPLE      = colors.HexColor("#7c6ffd")
DARK_BG     = colors.HexColor("#1a1a2e")
USER_BG     = colors.HexColor("#2d2b55")
ASST_BG     = colors.HexColor("#1e1e32")
TEXT_LIGHT  = colors.HexColor("#e2e2f0")
TEXT_MUTED  = colors.HexColor("#9090b0")


def generate_chat_pdf(chat_title: str, messages: list[dict]) -> bytes:
    """
    Generate a PDF document for the given chat.

    Args:
        chat_title: The chat session title.
        messages:   List of dicts with keys 'role' ('user'|'assistant') and 'content'.

    Returns:
        Raw PDF bytes.
    """
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f"DocuChat — {chat_title}",
        author="DocuChat",
    )

    styles = getSampleStyleSheet()

    # ─── Custom styles ────────────────────────────────────────────────────────
    title_style = ParagraphStyle(
        "ChatTitle",
        parent=styles["Heading1"],
        fontSize=20,
        textColor=PURPLE,
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=TEXT_MUTED,
        spaceAfter=12,
    )
    user_label_style = ParagraphStyle(
        "UserLabel",
        parent=styles["Normal"],
        fontSize=9,
        textColor=PURPLE,
        fontName="Helvetica-Bold",
        alignment=TA_RIGHT,
    )
    asst_label_style = ParagraphStyle(
        "AsstLabel",
        parent=styles["Normal"],
        fontSize=9,
        textColor=TEXT_MUTED,
        fontName="Helvetica-Bold",
        alignment=TA_LEFT,
    )
    user_msg_style = ParagraphStyle(
        "UserMessage",
        parent=styles["Normal"],
        fontSize=11,
        textColor=TEXT_LIGHT,
        leading=16,
        alignment=TA_RIGHT,
        spaceAfter=12,
    )
    asst_msg_style = ParagraphStyle(
        "AsstMessage",
        parent=styles["Normal"],
        fontSize=11,
        textColor=TEXT_LIGHT,
        leading=16,
        alignment=TA_LEFT,
        spaceAfter=12,
    )

    # ─── Build story ─────────────────────────────────────────────────────────
    story = []

    # Header
    story.append(Paragraph("📄 DocuChat", title_style))
    story.append(Paragraph(
        f"Chat: <b>{chat_title}</b> &nbsp;|&nbsp; Exported: "
        f"{datetime.now(timezone.utc).strftime('%B %d, %Y %H:%M UTC')}",
        subtitle_style,
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=PURPLE, spaceAfter=16))

    # Messages
    for msg in messages:
        role    = msg.get("role", "user")
        content = msg.get("content", "").replace("\n", "<br/>")

        if role == "user":
            story.append(Paragraph("You", user_label_style))
            story.append(Paragraph(content, user_msg_style))
        else:
            story.append(Paragraph("DocuChat AI", asst_label_style))
            story.append(Paragraph(content, asst_msg_style))

        story.append(Spacer(1, 4))

    doc.build(story)
    return buffer.getvalue()
