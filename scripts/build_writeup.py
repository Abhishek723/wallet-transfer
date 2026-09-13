"""Regenerate the submission PDF: install reportlab and run this from the repo root."""

import re
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

root = Path(__file__).resolve().parents[1]
output = root / "output/pdf/wallet-design.pdf"
output.parent.mkdir(parents=True, exist_ok=True)
document = SimpleDocTemplate(
    str(output),
    pagesize=A4,
    rightMargin=43,
    leftMargin=43,
    topMargin=35,
    bottomMargin=34,
    title="Wallet & P2P Transfer - Design and Reasoning",
    author="Abhishek723",
)
body = ParagraphStyle(
    "Body",
    fontName="Helvetica",
    fontSize=9.6,
    leading=12.7,
    alignment=TA_LEFT,
    textColor=colors.HexColor("#222222"),
    spaceAfter=8,
)
title = ParagraphStyle("Title", parent=body, fontName="Helvetica-Bold", fontSize=18, leading=22)
subtitle = ParagraphStyle("Subtitle", parent=body, fontSize=9, textColor=colors.HexColor("#555555"))
story = [
    Paragraph("Wallet &amp; P2P Transfer", title),
    Paragraph("Design and reasoning | Python, FastAPI, PostgreSQL | September 13, 2026", subtitle),
    Spacer(1, 5),
]
for block in (root / "docs/DESIGN.md").read_text().split("\n\n"):
    if block.startswith("#") or not block.strip():
        continue
    text = escape(" ".join(block.splitlines()))
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`(.+?)`", r'<font name="Courier" size="8.8">\1</font>', text)
    story.append(Paragraph(text, body))
document.build(story)
print(output)
