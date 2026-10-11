"""Checking documents. Pure functions: bytes in, a verdict out.

Unlike an image, a document cannot be rebuilt from its pixels, so it is stored as it arrived once
these checks and the malware scan pass. What keeps that safe is how it is delivered: only as an
attachment, from a private bucket, through a short lived signed link (never inline, never from
our own origin). The checks here refuse the obvious ways a document carries code: scripts and
launch actions in a PDF, and macros, embedded objects and archive bombs in an Office file.
"""

import io
import re
import zipfile
from dataclasses import dataclass

from django.conf import settings

PDF_FORBIDDEN = (b"/javascript", b"/js", b"/launch", b"/embeddedfile", b"/richmedia", b"/xfa")
OFFICE_PARTS = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "word/document.xml",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xl/workbook.xml",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": (
        "ppt/presentation.xml"
    ),
}
OFFICE_FORBIDDEN_PARTS = ("vbaproject", "/activex", "/embeddings/", "/oleobject", "/vbadata")
OFFICE_FORBIDDEN_SUFFIXES = (".exe", ".dll", ".bat", ".cmd", ".js", ".vbs", ".ps1", ".jar", ".scr")
MAX_ENTRIES = 5000
_HEX_ESCAPE = re.compile(rb"#([0-9A-Fa-f]{2})")


class DocumentRejected(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CheckedDocument:
    content_type: str
    size: int


def sniff(data: bytes) -> str | None:
    """The content type the bytes really are, from their first bytes and structure."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"PK\x03\x04"):
        try:
            names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        except zipfile.BadZipFile:
            return None
        for content_type, part in OFFICE_PARTS.items():
            if part in names and "[Content_Types].xml" in names:
                return content_type
    return None


def _check_pdf(data: bytes) -> None:
    if b"%%EOF" not in data[-2048:]:
        raise DocumentRejected("corrupt")
    # PDF names may hide letters as #xx escapes, so undo them before looking for active content.
    plain = _HEX_ESCAPE.sub(lambda m: bytes([int(m.group(1), 16)]), data).lower()
    if any(token in plain for token in PDF_FORBIDDEN):
        raise DocumentRejected("active_content")
    if b"/encrypt" in plain:
        raise DocumentRejected("encrypted")


def _check_office(data: bytes, declared_type: str) -> None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise DocumentRejected("corrupt") from exc
    infos = archive.infolist()
    if len(infos) > MAX_ENTRIES:
        raise DocumentRejected("too_many_parts")
    if sum(info.file_size for info in infos) > settings.UPLOAD_DOCUMENT_MAX_UNPACKED_BYTES:
        raise DocumentRejected("too_large_unpacked")
    names = [info.filename for info in infos]
    for info in infos:
        name = info.filename.lower()
        if info.flag_bits & 0x1:
            raise DocumentRejected("encrypted")
        if name.startswith("/") or ".." in name.split("/"):
            raise DocumentRejected("corrupt")
        if any(part in "/" + name for part in OFFICE_FORBIDDEN_PARTS) or name.endswith(
            OFFICE_FORBIDDEN_SUFFIXES
        ):
            raise DocumentRejected("active_content")
    if "[Content_Types].xml" not in names or OFFICE_PARTS[declared_type] not in names:
        raise DocumentRejected("type_mismatch")


def inspect(data: bytes, declared_type: str) -> CheckedDocument:
    """Verify an upload really is the document it claims to be, with nothing active inside."""
    if declared_type not in settings.UPLOAD_DOCUMENT_TYPES:
        raise DocumentRejected("type_not_allowed")
    actual = sniff(data)
    if actual != declared_type:
        raise DocumentRejected("type_mismatch")
    if declared_type == "application/pdf":
        _check_pdf(data)
    else:
        _check_office(data, declared_type)
    return CheckedDocument(declared_type, len(data))
