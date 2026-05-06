import re
from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, HRFlowable, Preformatted

# ─── Color palette ───────────────────────────────────────────────────────────
ACCENT_COLOR = colors.HexColor("#4b44e0")
BLACK        = colors.black
GREY         = colors.HexColor("#444444")
CODE_BG      = colors.HexColor("#f8f8f8")
CODE_BORDER  = colors.HexColor("#dddddd")


def format_text_markup(text: str) -> str:
    """
    Handle inline markdown: bold, italic, inline code.
    Must escape special HTML characters first to avoid ReportLab parsing errors.
    """
    # 1. Escape & first
    text = text.replace('&', '&amp;')
    # 2. Escape < and > only if they aren't part of our tags (very simple approach)
    text = text.replace('<', '&lt;').replace('>', '&gt;')
    
    # 3. Apply Markdown -> HTML tags
    # Bold: **text** or __text__
    text = re.sub(r'(\*\*|__)(.*?)\1', r'<b>\2</b>', text)
    # Italic: *text* or _text_
    text = re.sub(r'(\*|_)(.*?)\1', r'<i>\2</i>', text)
    # Inline code: `text`
    text = re.sub(r'`(.*?)`', r'<font face="Courier" color="#c41261">\1</font>', text)
    
    return text


def generate_chat_pdf(chat_title: str, messages: list[dict]) -> bytes:
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
    # Define styles explicitly using Helvetica and Helvetica-Bold
    
    title_style = ParagraphStyle(
        "ChatTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=24,
        textColor=BLACK,
        spaceAfter=10,
    )
    
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=GREY,
        spaceAfter=15,
    )
    
    label_style_user = ParagraphStyle(
        "LabelUser",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=ACCENT_COLOR,
        spaceBefore=12,
        spaceAfter=4,
    )
    
    label_style_asst = ParagraphStyle(
        "LabelAsst",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=GREY,
        spaceBefore=12,
        spaceAfter=4,
    )

    normal_text_style = ParagraphStyle(
        "NormalText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        textColor=BLACK,
        leading=16,
        spaceAfter=10,
    )
    
    h1_style = ParagraphStyle(
        "H1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        textColor=BLACK,
        spaceBefore=12,
        spaceAfter=6,
    )
    
    h2_style = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        textColor=BLACK,
        spaceBefore=10,
        spaceAfter=4,
    )
    
    bullet_item_style = ParagraphStyle(
        "BulletItem",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        textColor=BLACK,
        leading=16,
        leftIndent=20,
        firstLineIndent=0,
        spaceAfter=6,
    )
    
    code_block_style = ParagraphStyle(
        "CodeBlock",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=10,
        textColor=BLACK,
        backColor=CODE_BG,
        borderPadding=10,
        borderRadius=4,
        borderWidth=0.5,
        borderColor=CODE_BORDER,
        leading=13,
        leftIndent=10,
        rightIndent=10,
        spaceBefore=10,
        spaceAfter=10,
    )

    # ─── Build story ─────────────────────────────────────────────────────────
    story = []

    # Header
    story.append(Paragraph("DocuChat", title_style))
    story.append(Paragraph(
        f"Conversation: <b>{chat_title}</b> &nbsp;|&nbsp; Exported: "
        f"{datetime.now(timezone.utc).strftime('%B %d, %Y %H:%M UTC')}",
        subtitle_style,
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.black, spaceAfter=20))

    for msg in messages:
        role = msg.get("role", "user")
        raw_content = msg.get("content", "")

        # Role Label
        label = "You" if role == "user" else "DocuChat AI"
        story.append(Paragraph(label, label_style_user if role == "user" else label_style_asst))

        # 1. Extract Code Blocks
        parts = re.split(r'```(?:.*?)\n?(.*?)```', raw_content, flags=re.DOTALL)
        
        for i, part in enumerate(parts):
            if i % 2 == 1:
                # Code Block
                story.append(Preformatted(part.strip(), code_block_style))
            else:
                # Normal text - split into lines for headings and lists
                lines = part.split('\n')
                for line in lines:
                    s_line = line.strip()
                    if not s_line:
                        story.append(Spacer(1, 2))
                        continue

                    # Markdown Headings
                    if s_line.startswith('### '):
                        story.append(Paragraph(format_text_markup(s_line[4:]), h2_style))
                    elif s_line.startswith('## '):
                        story.append(Paragraph(format_text_markup(s_line[3:]), h1_style))
                    elif s_line.startswith('# '):
                        story.append(Paragraph(format_text_markup(s_line[2:]), h1_style))
                    
                    # Bullet Lists
                    elif s_line.startswith('- ') or s_line.startswith('* ') or s_line.startswith('+ '):
                        # Use a proper bullet point
                        bullet_txt = f"&bull; {format_text_markup(s_line[2:])}"
                        story.append(Paragraph(bullet_txt, bullet_item_style))
                    
                    # Numbered Lists
                    elif re.match(r'^\d+\. ', s_line):
                        story.append(Paragraph(format_text_markup(s_line), bullet_item_style))
                    
                    # Standard Paragraph
                    else:
                        story.append(Paragraph(format_text_markup(line), normal_text_style))

        story.append(Spacer(1, 8))

    doc.build(story)
    return buffer.getvalue()



