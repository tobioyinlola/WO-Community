"""Text rewritten for the ear before it is read aloud.

A speech model reads what it is given: "₦2.5m", "YC", "e.g." and a bullet list all come out
stilted. This turns written shorthand into what a person would actually say, so the voice can
sound like someone talking rather than someone reading.
"""

import re

# Said as words. Shorthand people do say as letters (MVP, CEO, KPI) is left for the voice.
_SAY = {
    "YC": "Y Combinator",
    "VC": "investor",
    "VCs": "investors",
    "B2B": "business to business",
    "B2C": "business to consumer",
    "SaaS": "software as a service",
    "CAC": "customer acquisition cost",
    "LTV": "lifetime value",
    "MRR": "monthly recurring revenue",
    "ARR": "annual recurring revenue",
    "GTM": "go to market",
    "PMF": "product market fit",
    "w/": "with",
    "e.g.": "for example",
    "eg.": "for example",
    "i.e.": "that is",
    "etc.": "and so on",
    "vs.": "versus",
    "vs": "versus",
    "approx.": "about",
    "&": "and",
}
_WORD = re.compile(
    r"(?<![\w.])("
    + "|".join(re.escape(k) for k in sorted(_SAY, key=len, reverse=True))
    + r")(?![\w])"
)

_CURRENCY = {"₦": "naira", "$": "dollars", "£": "pounds", "€": "euros", "KSh": "shillings"}
_SCALE = {"k": "thousand", "m": "million", "mn": "million", "b": "billion", "bn": "billion"}
_MONEY = re.compile(
    r"(₦|\$|£|€|KSh\s?)\s?(\d(?:[\d,]*\d)?(?:\.\d+)?)(?:\s?(k|mn|m|bn|b)\b)?", re.IGNORECASE
)
_CODE_MONEY = re.compile(
    r"\b(NGN|USD|KES|GHS|ZAR)\s?(\d(?:[\d,]*\d)?(?:\.\d+)?)(?:\s?(k|mn|m|bn|b)\b)?"
)
_CODES = {"NGN": "naira", "USD": "dollars", "KES": "shillings", "GHS": "cedis", "ZAR": "rand"}


def _amount(number: str, scale: str | None) -> str:
    value = number.replace(",", "")
    if scale:
        return f"{value} {_SCALE[scale.lower()]}"
    digits = value.split(".")[0]
    # Large round figures read better as "2 million" than as seven digits.
    for size, word in ((1_000_000_000, "billion"), (1_000_000, "million")):
        whole = int(digits) if digits.isdigit() else 0
        if whole >= size and "." not in value:
            short = f"{whole / size:.1f}".rstrip("0").rstrip(".")
            return f"{short} {word}"
    return value


def for_speech(text: str) -> str:
    """``text`` as it should be said."""
    out = text
    out = re.sub(
        r"https?://\S+?(?=[.,;:!?]?(?:\s|$))|www\.\S+?(?=[.,;:!?]?(?:\s|$))",
        "the link in the chat",
        out,
    )
    out = re.sub(r"the link in the chat\s*\n", "the link in the chat.\n", out)
    out = re.sub(r"[*_`#>]+", "", out)  # markdown marks
    # List items become sentences, so each gets its own breath.
    out = re.sub(r"(?m)^\s*(?:[-•]|\d+[.)])\s+(.*?)[.;:]?\s*$", r"\1.", out)
    out = _MONEY.sub(
        lambda m: f"{_amount(m.group(2), m.group(3))} {_CURRENCY[m.group(1).strip()]}", out
    )
    out = _CODE_MONEY.sub(lambda m: f"{_amount(m.group(2), m.group(3))} {_CODES[m.group(1)]}", out)
    out = re.sub(r"(\d)\s?%", r"\1 percent", out)
    out = re.sub(r"(\d)\s?[xX]\b", r"\1 times", out)
    out = re.sub(r"(\d)\s?[-–]\s?(\d)", r"\1 to \2", out)
    # Two pieces of shorthand side by side are a pair ("CAC/LTV"); two words are a choice.
    out = re.sub(r"\b([A-Z]{2,})/([A-Z]{2,})\b", r"\1 and \2", out)
    out = _WORD.sub(lambda m: _SAY[m.group(1)], out)
    out = re.sub(r"(?<=[a-z])/(?=[a-z])", " or ", out)
    out = re.sub(r"\s*\n+\s*", " ", out)  # paragraphs: the full stops already give the pauses
    out = re.sub(r"\.{2,}", ".", out)
    return re.sub(r"\s{2,}", " ", out).strip()
