"""A one-page certificate as a PDF, written directly so no extra library is needed.

Only the standard Helvetica font is used, which covers Western European letters. Characters outside
that range are shown as "?" rather than breaking the file.
"""

from datetime import datetime

PAGE_WIDTH, PAGE_HEIGHT = 842, 595  # A4 landscape in points


def _text(value: str) -> bytes:
    """The text as PDF string bytes, escaped."""
    raw = value.encode("cp1252", errors="replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _centred(value: str, size: int, y: int, font: str = "F1") -> bytes:
    width = len(value) * size * 0.5  # Helvetica averages about half the point size per letter
    x = max(40, (PAGE_WIDTH - width) / 2)
    return b"BT /%b %d Tf %.1f %d Td (%b) Tj ET\n" % (font.encode(), size, x, y, _text(value))


def _shorten(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def render_certificate(
    *, holder: str, course: str, issued_at: datetime, code: str, verify_url: str
) -> bytes:
    content = b"".join(
        [
            b"2 w 40 40 %d %d re S\n" % (PAGE_WIDTH - 80, PAGE_HEIGHT - 80),
            _centred("WO Community", 22, 505, "F2"),
            _centred("Certificate of Completion", 34, 440, "F2"),
            _centred("This certifies that", 16, 380),
            _centred(_shorten(holder, 60), 30, 335, "F2"),
            _centred("has successfully completed the course", 16, 290),
            _centred(_shorten(course, 70), 24, 250, "F2"),
            _centred(f"Issued {issued_at:%d %B %Y}", 14, 180),
            _centred(f"Certificate code {code}", 12, 110),
            _centred(f"Verify at {verify_url}", 10, 90),
        ]
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>" % (PAGE_WIDTH, PAGE_HEIGHT),
        b"<< /Length %d >>\nstream\n%b\nendstream" % (len(content), content),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%b\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)
