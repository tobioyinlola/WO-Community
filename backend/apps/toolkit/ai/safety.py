"""Rules about what the assistant must not do, enforced before and after a model is called.

The prompts say the same things, but a rule that only lives in a prompt is a request. These
checks run in code so the behaviour does not depend on a model choosing to comply.
"""

import re
from dataclasses import dataclass

DECLINE_ADVICE = (
    "I cannot give legal, tax or investment advice. For that, please speak to a qualified "
    "professional: a lawyer, an accountant, or a licensed adviser. I can help you prepare "
    "your questions and organise the facts about your venture so the conversation is quicker."
)
DECLINE_DECEPTION = (
    "I cannot help present results, customers, reviews or traction that are not real. I can "
    "help you describe what you actually have, and plan how to earn the proof you need."
)

_ADVICE = {
    "legal": re.compile(
        r"\b(is it legal|legally|sue|lawsuit|contract clause|terms and conditions for|"
        r"incorporat\w+ (?:in|as)|shareholders? agreement|trademark|patent|liable|liability|"
        r"gdpr compliance|data protection law|legal advice|"
        r"draft (?:a|an|the) (?:contract|nda|agreement))\b",
        re.IGNORECASE,
    ),
    "tax": re.compile(
        r"\b(tax(?:es|ation)?\b|vat\b|paye\b|withholding|tax advice|tax exempt|tax return|"
        r"corporate tax|capital gains)",
        re.IGNORECASE,
    ),
    "investment": re.compile(
        r"\b(should i invest|which stocks?|buy shares|investment advice|"
        r"is .{0,40} a good investment|invest my (?:savings|money)|securities offering|"
        r"valuation (?:i|we) should accept|accept (?:this|the) term sheet)",
        re.IGNORECASE,
    ),
}
_DECEPTION = re.compile(
    r"\b(fake|made[- ]up|invent(?:ed)?|fabricate\w*|pretend|inflate|exaggerate)\b.{0,60}"
    r"\b(traction|customers?|users?|revenue|testimonials?|reviews?|logos?|partners?|"
    r"numbers|metrics|growth)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Screening:
    advice: str | None = None  # "legal", "tax" or "investment"
    deception: bool = False

    @property
    def blocked(self) -> bool:
        return self.advice is not None or self.deception

    @property
    def reply(self) -> str:
        if self.deception:
            return DECLINE_DECEPTION
        return DECLINE_ADVICE


def screen(message: str) -> Screening:
    """Whether a member's message asks for something the assistant must decline."""
    if _DECEPTION.search(message):
        return Screening(deception=True)
    for kind, pattern in _ADVICE.items():
        if pattern.search(message):
            return Screening(advice=kind)
    return Screening()


_INSTRUCTION_LEAK = re.compile(
    r"(<<<\s*(?:END )?DATA|ignore (?:all )?(?:previous|prior|above) (?:instructions|rules)|"
    r"as an? (?:ai|language model)|my (?:system )?(?:instructions|prompt) (?:are|is|say))",
    re.IGNORECASE,
)


def leaks_instructions(text: str) -> bool:
    """Whether an answer repeats our delimiters or talks about its own instructions."""
    return bool(_INSTRUCTION_LEAK.search(text))
