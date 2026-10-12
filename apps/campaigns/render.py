"""Newsletter content: validated blocks, rendered on the server with everything escaped.

The editor (a front-end concern) sends a list of blocks. Each block type has a fixed shape and
text is escaped when rendered, so nothing an admin types can inject markup or scripts into mail.
Merge fields are limited to a fixed list and are substituted last, as escaped text.
"""

import re
from typing import Any
from uuid import UUID

from django.conf import settings
from django.utils.html import escape
from rest_framework import exceptions

from apps.core.text import clean_url, plain, rich_comment, text_of
from apps.uploads import services as uploads

MERGE_FIELDS = ("first_name",)
MERGE_TOKEN = re.compile(r"\{\{\s*([a-zA-Z_]+)\s*\}\}")
BLOCK_TYPES = ("heading", "paragraph", "button", "image", "divider")
MAX_BLOCKS = 40
FALLBACK_NAME = "there"


def _invalid(message: str) -> exceptions.ValidationError:
    return exceptions.ValidationError({"blocks": [message]})


def check_merge_fields(text: str) -> None:
    unknown = {m for m in MERGE_TOKEN.findall(text) if m not in MERGE_FIELDS}
    if unknown:
        allowed = ", ".join("{{" + f + "}}" for f in MERGE_FIELDS)
        raise _invalid(f"Unknown merge field: {', '.join(sorted(unknown))}. Use {allowed}.")


def _url(value: Any) -> str:
    try:
        cleaned = clean_url(str(value))
    except exceptions.ValidationError as exc:
        raise _invalid(" ".join(str(m) for m in exc.detail)) from exc
    if not cleaned:
        raise _invalid("A link is required.")
    return cleaned


def clean_blocks(blocks: Any, *, owner_id: UUID) -> list[dict[str, Any]]:
    """Validate blocks and return them in the form stored (text cleaned, images claimed)."""
    if not isinstance(blocks, list) or not blocks or len(blocks) > MAX_BLOCKS:
        raise _invalid(f"Provide between 1 and {MAX_BLOCKS} blocks.")
    cleaned: list[dict[str, Any]] = []
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") not in BLOCK_TYPES:
            raise _invalid("Each block needs a type: " + ", ".join(BLOCK_TYPES) + ".")
        kind = block["type"]
        allowed = {
            "heading": {"type", "text", "level"},
            "paragraph": {"type", "html"},
            "button": {"type", "label", "url"},
            "image": {"type", "upload_id", "image_key", "alt", "url"},
            "divider": {"type"},
        }[kind]
        if set(block) - allowed:
            raise _invalid(f"Unknown field in a {kind} block.")
        if kind == "heading":
            text = plain(str(block.get("text", "")))
            if not text or len(text) > 150:
                raise _invalid("A heading needs 1 to 150 characters.")
            check_merge_fields(text)
            level = block.get("level", 2)
            if level not in (1, 2):
                raise _invalid("Heading level must be 1 or 2.")
            cleaned.append({"type": "heading", "text": text, "level": level})
        elif kind == "paragraph":
            markup = rich_comment(str(block.get("html", "")))
            if not text_of(markup) or len(text_of(markup)) > 3000:
                raise _invalid("A paragraph needs 1 to 3000 characters.")
            check_merge_fields(markup)
            cleaned.append({"type": "paragraph", "html": markup})
        elif kind == "button":
            label = plain(str(block.get("label", "")))
            if not label or len(label) > 40:
                raise _invalid("A button label needs 1 to 40 characters.")
            check_merge_fields(label)
            cleaned.append({"type": "button", "label": label, "url": _url(block.get("url"))})
        elif kind == "image":
            cleaned.append(_image_block(block, owner_id))
        else:
            cleaned.append({"type": "divider"})
    return cleaned


def _image_block(block: dict[str, Any], owner_id: UUID) -> dict[str, Any]:
    key = block.get("image_key", "")
    if block.get("upload_id"):
        upload = uploads.claim(
            upload_id=block["upload_id"], owner_id=owner_id, purpose="campaign_image"
        )
        key = upload.base_key
    elif key and not str(key).startswith("media/campaign_image/"):
        raise _invalid("Unknown image.")  # a kept image must be one of ours
    if not key:
        raise _invalid("An image block needs an upload.")
    result: dict[str, Any] = {
        "type": "image",
        "image_key": key,
        "alt": plain(str(block.get("alt", "")))[:200],
    }
    if block.get("url"):
        result["url"] = _url(block["url"])
    return result


def _merge(text: str, values: dict[str, str], *, escape_values: bool) -> str:
    def replace(match: re.Match[str]) -> str:
        value = values.get(match.group(1), "")
        return escape(value) if escape_values else value

    return MERGE_TOKEN.sub(replace, text)


def _button_html(label: str, url: str) -> str:
    return (
        '<p style="margin:24px 0"><a href="' + escape(url) + '" style="background:#1a56db;'
        "color:#ffffff;padding:12px 22px;border-radius:6px;text-decoration:none;"
        'display:inline-block;font-weight:600">' + escape(label) + "</a></p>"
    )


def render(
    *,
    preheader: str,
    blocks: list[dict[str, Any]],
    first_name: str,
    unsubscribe_url: str,
) -> tuple[str, str]:
    """The email as (html, plain text) for one recipient."""
    values = {"first_name": first_name or FALLBACK_NAME}
    body_html: list[str] = []
    body_text: list[str] = []
    for block in blocks:
        kind = block["type"]
        if kind == "heading":
            text = _merge(block["text"], values, escape_values=False)
            tag = f"h{block['level']}"
            body_html.append(f'<{tag} style="margin:24px 0 8px">{escape(text)}</{tag}>')
            body_text.append(text.upper() if block["level"] == 1 else text)
        elif kind == "paragraph":
            body_html.append(_merge(block["html"], values, escape_values=True))
            body_text.append(_merge(text_of(block["html"]), values, escape_values=False))
        elif kind == "button":
            label = _merge(block["label"], values, escape_values=False)
            body_html.append(_button_html(label, block["url"]))
            body_text.append(f"{label}: {block['url']}")
        elif kind == "image":
            image = uploads.image_urls(block["image_key"])
            if image:
                tag = (
                    f'<img src="{escape(image["large"])}" alt="{escape(block["alt"])}" '
                    'style="max-width:100%;height:auto;border-radius:6px">'
                )
                if block.get("url"):
                    tag = f'<a href="{escape(block["url"])}">{tag}</a>'
                body_html.append(f'<p style="margin:16px 0">{tag}</p>')
                if block["alt"]:
                    body_text.append(f"[{block['alt']}]")
        else:
            body_html.append('<hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0">')
            body_text.append("-----")
    footer_text = (
        f"{settings.CAMPAIGN_FOOTER}\n"
        "You are receiving this because you opted in to news from WO Community.\n"
        f"Unsubscribe: {unsubscribe_url}"
    )
    hidden_preheader = (
        f'<div style="display:none;max-height:0;overflow:hidden">{escape(preheader)}</div>'
        if preheader
        else ""
    )
    page = (
        '<!doctype html><html><body style="margin:0;background:#f3f4f6;font-family:Arial,'
        'sans-serif;color:#111827"><div style="max-width:600px;margin:0 auto;background:#ffffff;'
        f'padding:24px">{hidden_preheader}{"".join(body_html)}'
        '<hr style="border:none;border-top:1px solid #e5e7eb;margin:32px 0 16px">'
        f'<p style="font-size:12px;color:#6b7280">{escape(settings.CAMPAIGN_FOOTER)}<br>'
        "You are receiving this because you opted in to news from WO Community.<br>"
        f'<a href="{escape(unsubscribe_url)}">Unsubscribe</a></p></div></body></html>'
    )
    text = "\n\n".join(body_text) + "\n\n--\n" + footer_text
    return page, text
