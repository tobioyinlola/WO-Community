"""The certificate of completion as a one page A4 landscape PDF.

The layout follows the design specification for certificates: a cream canvas with a thin forest
border, the logo and the eyebrow along the top, the learner and the course on the left, a forest
arch with the brand shapes on the right, the signatory's name at the bottom left and the
certificate ID in the
details row. There is no QR code and no web address on the page; the ID is looked up on the
verification page. The same arrangement is shown on screen by the front
end (`CertificateSheet`), so the preview an administrator edits matches what members receive.

It is drawn directly with ReportLab rather than through an HTML engine: no browser or system
libraries are needed on the servers, fonts are embedded (so the text stays selectable and the file
small) and the output is the same everywhere. Colours are the design tokens converted to hex here;
`test_certificate_pdf` checks they still match `frontend/src/styles/tokens.css`.
"""

import io
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ASSETS = Path(__file__).parent / "assets"
FONT_DIR = ASSETS / "fonts"
LOGO = ASSETS / "wo-logo-on-light.png"  # from the design system; a wordmark stands in if missing
# Onyeka's own signature, signed over the line whenever the certificate names him and no other
# signature has been uploaded.
DEFAULT_SIGNATURE = ASSETS / "signature-onyeka.png"

PAGE_WIDTH, PAGE_HEIGHT = 842, 595  # A4 landscape in points (297 by 210 mm)
MM = 72 / 25.4

# Design tokens (frontend/src/styles/tokens.css) as hex, for print.
COLOURS = {
    "cream-200": "#EEEBE3",
    "forest-700": "#06372F",
    "gold-500": "#B88917",
    "gold-700": "#76560B",
    "tint-periwinkle": "#ABBDFF",
    "tint-peach": "#FFC9AA",
    "text-secondary": "#3C5A52",
}

FONTS = {
    "regular": ("HankenGrotesk", "HankenGrotesk-Regular.ttf"),
    "bold": ("HankenGrotesk-Bold", "HankenGrotesk-Bold.ttf"),
    "heavy": ("HankenGrotesk-ExtraBold", "HankenGrotesk-ExtraBold.ttf"),
    "mono": ("JetBrainsMono", "JetBrainsMono-Medium.ttf"),
}

LEFT = 60
DEFAULT_SIGNATORY = "Onyeka Akumah"
TEXT_WIDTH = round(PAGE_WIDTH * 0.6)  # the centre block is 60 percent of the page


@dataclass(frozen=True)
class CertificateContent:
    holder: str
    course: str
    issued_at: datetime
    number: str
    hours: Decimal
    title_text: str = "Certificate of completion"
    signatory_name: str = ""
    signature_png: bytes | None = None  # an uploaded signature; None falls back to the default


def _c(name: str) -> HexColor:
    return HexColor(COLOURS[name])


@lru_cache(maxsize=1)
def _register() -> None:
    for name, file in FONTS.values():
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))


def _font(key: str) -> str:
    _register()
    return FONTS[key][0]


def _printable(text: str, font: str) -> str:
    """Keep what the font can draw. A letter it lacks falls back to its plain form, else '?'."""
    face = pdfmetrics.getFont(font).face
    out = []
    for ch in unicodedata.normalize("NFC", text):
        if unicodedata.combining(ch):
            continue  # a mark left over after composing would be drawn as a stray, spaced character
        if ord(ch) in face.charToGlyph:
            out.append(ch)
            continue
        base = unicodedata.normalize("NFD", ch)[0]
        out.append(base if ord(base) in face.charToGlyph else "?")
    return "".join(out)


def _tracked(
    pdf: canvas.Canvas, x: float, y: float, text: str, font: str, size: float, space: float
):
    """Text with extra space between the letters, left aligned at x."""
    obj = pdf.beginText(x, y)
    obj.setFont(font, size)
    obj.setCharSpace(space)
    obj.textOut(text)
    obj.setCharSpace(0)  # character spacing would otherwise carry on into the text that follows
    pdf.drawText(obj)


def _tracked_width(text: str, font: str, size: float, space: float) -> float:
    return pdfmetrics.stringWidth(text, font, size) + space * len(text)


def _fit(text: str, font: str, size: float, floor: float, width: float) -> float:
    """The largest size down to `floor` at which the text fits in `width`."""
    while size > floor and pdfmetrics.stringWidth(text, font, size) > width:
        size -= 1
    return size


def _decoration(pdf: canvas.Canvas) -> None:
    """The right hand side: a forest arch bleeding off the top and right with the brand shapes."""
    slab_left, slab_bottom = 640, 165
    pdf.setFillColor(_c("forest-700"))
    pdf.roundRect(
        slab_left,
        slab_bottom,
        PAGE_WIDTH - slab_left + 120,
        PAGE_HEIGHT - slab_bottom + 120,
        radius=90,
        stroke=0,
        fill=1,
    )
    # the large ochre ring with an "eye" dot, as in the logo
    cx, cy = 742, 440
    pdf.setStrokeColor(_c("gold-500"))
    pdf.setLineWidth(18)
    pdf.circle(cx, cy, 62, stroke=1, fill=0)
    pdf.setFillColor(_c("cream-200"))
    pdf.circle(cx + 4, cy + 4, 13, stroke=0, fill=1)
    # a periwinkle capsule and a peach circle
    pdf.setFillColor(_c("tint-periwinkle"))
    pdf.roundRect(668, 250, 96, 40, radius=20, stroke=0, fill=1)
    pdf.setFillColor(_c("tint-peach"))
    pdf.circle(790, 232, 24, stroke=0, fill=1)


# The full logo is never printed narrower than 28 mm (design system, section 03).
LOGO_WIDTH = 30 * MM
LOGO_HEIGHT = LOGO_WIDTH * 578 / 680  # the supplied file is 680 by 578


def _logo(pdf: canvas.Canvas) -> None:
    top = PAGE_HEIGHT - 66
    if LOGO.exists():
        pdf.drawImage(
            ImageReader(str(LOGO)),
            LEFT,
            PAGE_HEIGHT - 44 - LOGO_HEIGHT,
            width=LOGO_WIDTH,
            height=LOGO_HEIGHT,
            mask="auto",
        )
        return
    pdf.setFillColor(_c("forest-700"))
    pdf.setFont(_font("heavy"), 17)
    pdf.drawString(LEFT, top + 4, "WO COMMUNITY")


def _details(pdf: canvas.Canvas, content: CertificateContent, y: float) -> None:
    hours = f"{content.hours.normalize():f}" if content.hours else "0"
    items = [
        ("Date of completion", f"{content.issued_at:%d %B %Y}".lstrip("0"), "bold", 13),
        ("Course length", f"{hours} {'hour' if hours == '1' else 'hours'}", "bold", 13),
        ("Certificate ID", content.number, "mono", 11),
    ]
    x = LEFT
    for label, value, face, size in items:
        pdf.setFillColor(_c("gold-700"))
        _tracked(pdf, x, y + 22, label.upper(), _font("bold"), 7.5, 1.1)
        pdf.setFillColor(_c("forest-700"))
        pdf.setFont(_font(face), size)
        pdf.drawString(x, y, _printable(value, _font(face)))
        x += max(
            120.0,
            pdfmetrics.stringWidth(value, _font(face), size) + 36,
            _tracked_width(label.upper(), _font("bold"), 7.5, 1.1) + 24,
        )


def _signature_image(content: CertificateContent) -> ImageReader | None:
    if content.signature_png:
        return ImageReader(io.BytesIO(content.signature_png))
    named = content.signatory_name or DEFAULT_SIGNATORY
    if named == DEFAULT_SIGNATORY and DEFAULT_SIGNATURE.exists():
        return ImageReader(str(DEFAULT_SIGNATURE))
    return None


def _signature(pdf: canvas.Canvas, content: CertificateContent) -> None:
    """The signature over a rule, the signatory's name under it and a small uppercase label."""
    line_y = 112
    image = _signature_image(content)
    if image is not None:
        width, height = image.getSize()
        scale = min(165 / width, 66 / height)
        pdf.drawImage(image, LEFT, line_y + 2, width * scale, height * scale, mask="auto")
    pdf.setStrokeColor(_c("forest-700"))
    pdf.setLineWidth(0.8)
    pdf.line(LEFT, line_y, LEFT + 190, line_y)
    name = _printable(content.signatory_name or DEFAULT_SIGNATORY, _font("bold"))
    size = _fit(name, _font("bold"), 13, 8, 190)
    pdf.setFillColor(_c("forest-700"))
    pdf.setFont(_font("bold"), size)
    pdf.drawString(LEFT, line_y - 16, name)
    pdf.setFillColor(_c("gold-700"))
    _tracked(pdf, LEFT, line_y - 29, "WO COMMUNITY", _font("bold"), 7.5, 1.1)


def render_certificate(content: CertificateContent) -> bytes:
    _register()
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT), pageCompression=1)
    pdf.setTitle(f"{content.title_text}: {content.holder}")
    pdf.setAuthor("WO Community")
    pdf.setSubject(f"Certificate {content.number}")

    pdf.setFillColor(_c("cream-200"))  # full bleed, never pure white
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, stroke=0, fill=1)
    _decoration(pdf)
    inset = 10 * MM
    pdf.setStrokeColor(_c("forest-700"))
    pdf.setLineWidth(0.75)
    pdf.roundRect(
        inset, inset, PAGE_WIDTH - 2 * inset, PAGE_HEIGHT - 2 * inset, radius=20, stroke=1, fill=0
    )

    _logo(pdf)
    eyebrow = _printable(content.title_text.upper(), _font("bold"))
    width = _tracked_width(eyebrow, _font("bold"), 9, 1.44)
    pdf.setFillColor(_c("gold-700"))
    _tracked(pdf, 610 - width, PAGE_HEIGHT - 60, eyebrow, _font("bold"), 9, 1.44)

    pdf.setFillColor(_c("text-secondary"))
    pdf.setFont(_font("regular"), 13)
    pdf.drawString(LEFT, 412, "This certifies that")

    holder = _printable(content.holder, _font("heavy"))
    size = _fit(holder, _font("heavy"), 44, 24, TEXT_WIDTH)
    pdf.setFillColor(_c("forest-700"))
    pdf.setFont(_font("heavy"), size)
    pdf.drawString(LEFT, 366, holder)
    pdf.setStrokeColor(_c("forest-700"))
    pdf.setLineWidth(3)
    rule = min(TEXT_WIDTH, pdfmetrics.stringWidth(holder, _font("heavy"), size))
    pdf.line(LEFT, 354, LEFT + rule, 354)

    pdf.setFillColor(_c("text-secondary"))
    pdf.setFont(_font("regular"), 13)
    pdf.drawString(LEFT, 322, "has successfully completed")

    course = _printable(content.course, _font("bold"))
    lines = simpleSplit(course, _font("bold"), 24, TEXT_WIDTH)[:2]
    if len(simpleSplit(course, _font("bold"), 24, TEXT_WIDTH)) > 2:
        lines[-1] = lines[-1].rstrip() + "…"
    pdf.setFillColor(_c("forest-700"))
    pdf.setFont(_font("bold"), 24)
    y = 290
    for line in lines:
        pdf.drawString(LEFT, y, line)
        y -= 30

    _details(pdf, content, 205)
    _signature(pdf, content)
    pdf.setFillColor(_c("text-secondary"))
    pdf.setFont(_font("regular"), 8.5)
    pdf.drawString(LEFT, 42, "The future of Africa is being built here.")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
