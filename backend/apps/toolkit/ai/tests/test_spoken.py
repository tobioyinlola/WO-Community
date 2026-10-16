import pytest

from apps.toolkit.ai.spoken import for_speech


@pytest.mark.parametrize(
    ("written", "said"),
    [
        ("Aim for 5-7% a week.", "Aim for 5 to 7 percent a week."),
        ("From ₦2,500,000 to ₦5m.", "From 2.5 million naira to 5 million naira."),
        ("Charge $20, or $1.5k a year.", "Charge 20 dollars, or 1.5 thousand dollars a year."),
        ("NGN 40000 per month.", "40000 naira per month."),
        (
            "YC wants PMF & users, e.g. ten.",
            "Y Combinator wants product market fit and users, for example ten.",
        ),
        (
            "Watch CAC/LTV and buyers/sellers.",
            "Watch customer acquisition cost and lifetime value and buyers or sellers.",
        ),
        ("Grow 3x.", "Grow 3 times."),
        (
            "Read https://ycombinator.com/apply, then apply.",
            "Read the link in the chat, then apply.",
        ),
        ("Do this:\n- Talk to users\n- **Ship** weekly", "Do this: Talk to users. Ship weekly."),
        ("Keep the MVP small.", "Keep the MVP small."),
    ],
)
def test_written_shorthand_is_turned_into_what_a_person_would_say(written, said):
    assert for_speech(written) == said
