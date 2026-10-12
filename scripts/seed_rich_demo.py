# ruff: noqa: E501, E402, S112
"""Adds a lived-in community on top of ``seed_demo.py``, so every screen has real-looking content.

Run after ``seed_demo.py`` (and ``seed_admin_demo.py`` if you use the admin console):

    DJANGO_SETTINGS_MODULE=config.settings.local python scripts/seed_rich_demo.py

It adds startups with descriptions, websites, pitch deck links, traction and open jobs, more
members, posts with comments and reactions, events, news and video courses with outlines. The
companies and people are made up and their links point at reserved ``.example`` addresses. The
course videos are real, public Y Combinator Startup School talks. Safe to run twice: it stops
when the extra members already exist. Refuses to run outside local settings.
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.utils import timezone  # noqa: E402

if not settings.DEBUG:
    sys.exit("Refusing to seed demo data outside local development.")

from apps.accounts.models import User, UserRole, UserStatus  # noqa: E402
from apps.core.etag import etag_for  # noqa: E402
from apps.directory import services as directory  # noqa: E402
from apps.editorial import services as editorial  # noqa: E402
from apps.editorial.models import EditorialItem  # noqa: E402
from apps.events import services as events  # noqa: E402
from apps.events.models import Event  # noqa: E402
from apps.feed import follows  # noqa: E402
from apps.feed import services as feed
from apps.feed.models import Post  # noqa: E402
from apps.jobs import services as jobs  # noqa: E402
from apps.jobs.models import JobSettings  # noqa: E402
from apps.learning import authoring as learning  # noqa: E402
from apps.learning import learn, lms  # noqa: E402
from apps.learning.models import (
    Course,  # noqa: E402
    Lesson,  # noqa: E402
)
from apps.profiles import services as profiles  # noqa: E402
from apps.reference import selectors as reference  # noqa: E402
from apps.startups import services as startups  # noqa: E402
from apps.startups.models import Startup  # noqa: E402

PASSWORD = "Demo-Passw0rd-2026"  # nosec B105  # noqa: S105  # local demo data only
MARKER = "yetunde@demo.test"

# Details for the ten startups that seed_demo.py created, keyed by owner email:
# description, year founded, traction (kind, value) and open roles.
EXISTING = {
    "amaka@demo.test": (
        "Kuda Foods collects produce from more than 600 smallholder farms around Lagos and "
        "delivers it to restaurants, canteens and street-side kitchens within a day. Farmers "
        "are paid within 48 hours and buyers get fresher stock at a lower price than the open "
        "market.\n\nWe run our own cold-chain hubs in Ikorodu and Lekki and plan to open in "
        "Ibadan and Abuja next year.",
        2022,
        [("users", 1850), ("revenue_range", "50k_250k"), ("milestone", "600 farms onboarded")],
        ["Head of supply, Lagos"],
    ),
    "tunde@demo.test": (
        "Delta Capital backs African fintech founders at pre-seed and seed with cheques from "
        "$100k to $500k. We have invested in 18 companies across Kenya, Nigeria, Ghana and "
        "Egypt, and we help portfolio founders with hiring, regulation and follow-on rounds.",
        2019,
        [
            ("funding_range", "gt_5m"),
            ("milestone", "18 portfolio companies"),
            ("partner", "AfriVC Network"),
        ],
        [],
    ),
    "ngozi@demo.test": (
        "Paylane lets employers pay informal and hourly workers the same day they work, "
        "through mobile money, with no bank account needed. Workers can take part of their "
        "wages early at a small flat fee instead of borrowing from loan sharks.",
        2023,
        [
            ("users", 9200),
            ("revenue_range", "10k_50k"),
            ("award", "Accra Fintech Challenge winner"),
        ],
        ["Backend engineer (Python)", "Customer success lead"],
    ),
    "jide@demo.test": (
        "Shelf Africa gives neighbourhood shops a simple phone app to track stock, reorder from "
        "wholesalers and get credit against their sales history. Over 3,000 shops in Abuja, "
        "Kano and Port Harcourt order through us each week.",
        2021,
        [
            ("users", 3100),
            ("revenue_range", "50k_250k"),
            ("milestone", "Reached 3,000 active shops"),
        ],
        ["Growth marketing manager"],
    ),
    "zanele@demo.test": (
        "SolarGrid sells pay-as-you-go rooftop solar kits to township households and small "
        "businesses, paid in small weekly instalments. A kit replaces paraffin and cuts a "
        "family's energy bill by about a third.",
        2020,
        [("users", 5400), ("revenue_range", "gt_250k"), ("partner", "Eskom Energy Fund")],
        ["Field operations manager", "Solar installer (Cape Town)"],
    ),
    "chidi@demo.test": (
        "Medlink lets people book and pay for a clinic visit from any phone, including a basic "
        "USSD menu for people without data. Clinics fill empty slots and patients skip the "
        "queue. Live with 140 clinics in Lagos and Ibadan.",
        2022,
        [("users", 22000), ("revenue_range", "10k_50k"), ("milestone", "140 clinics live")],
        ["Mobile engineer (React Native)"],
    ),
    "funmi@demo.test": (
        "LearnLoop builds exam practice that works fully offline on low-cost Android phones. "
        "Students download a week of questions on Wi-Fi and practise anywhere, with a teacher "
        "dashboard that shows who needs help.",
        2024,
        [("users", 800), ("milestone", "Pilot with 6 secondary schools")],
        [],
    ),
    "kwame@demo.test": (
        "TroTro Track shows live minibus arrival times for commuters in Kumasi and Accra, "
        "built from GPS data shared by drivers who are paid per trip they share. It helps "
        "people leave home at the right time instead of waiting an hour at the stop.",
        2021,
        [("users", 12500), ("revenue_range", "1k_10k"), ("award", "Ghana Tech Awards finalist")],
        ["Data analyst"],
    ),
    "aisha@demo.test": (
        "Tisseo is a marketplace for West African textile makers, connecting weavers and dyers "
        "in Dakar, Bamako and Abidjan with fashion brands that want authentic, traceable "
        "fabric. We handle quality checks, export paperwork and payment.",
        2022,
        [("users", 410), ("revenue_range", "10k_50k"), ("milestone", "Shipped to 9 countries")],
        ["Operations coordinator, Dakar"],
    ),
    "samuel@demo.test": (
        "Habesha Pay sends money to and from Ethiopia at a fraction of the usual cost, with "
        "transfers that arrive in minutes into bank accounts and mobile wallets. Built with "
        "diaspora communities in the US, UK and Gulf states.",
        2021,
        [("users", 17800), ("revenue_range", "50k_250k"), ("partner", "Dashen Bank")],
        ["Compliance analyst"],
    ),
}

# Extra members, each founding a startup:
# name, email, country, city, headline, (startup, sector, stage, pitch), skills, description,
# year, traction, open roles
MORE = [
    (
        "Yetunde Balogun",
        MARKER,
        "NG",
        "Lagos",
        "Founder and CEO at Cowrie Books",
        (
            "Cowrie Books",
            "fintech",
            "pre-seed",
            "Bookkeeping that small traders can use from WhatsApp.",
        ),
        ["accounting", "product-management"],
        "Cowrie Books turns a trader's WhatsApp messages into proper accounts: sales, expenses "
        "and who owes what. Traders get a monthly report they can show a bank.",
        2024,
        [("users", 2300), ("milestone", "Listed on the Paystack partner directory")],
        ["Founding engineer"],
    ),
    (
        "Wanjiru Mwangi",
        "wanjiru@demo.test",
        "KE",
        "Nairobi",
        "Co-founder at Mkulima Direct",
        (
            "Mkulima Direct",
            "agritech",
            "seed",
            "Connecting maize and bean farmers straight to millers.",
        ),
        ["supply-chain", "operations"],
        "Mkulima Direct buys grain directly from cooperatives and sells to millers on contract, "
        "cutting out three layers of middlemen. Farmers earn about 18% more per bag.",
        2021,
        [("users", 7600), ("revenue_range", "gt_250k"), ("partner", "Kenya Farmers Union")],
        ["Procurement manager", "Logistics coordinator"],
    ),
    (
        "Oluwaseun Adebayo",
        "seun@demo.test",
        "NG",
        "Lagos",
        "CEO at Rida Freight",
        (
            "Rida Freight",
            "logistics",
            "series-a",
            "Truck booking and tracking for West African freight.",
        ),
        ["operations", "strategy"],
        "Rida Freight matches businesses that need to move goods with vetted truck owners, "
        "with live tracking and escrow payment. 4,200 trucks are on the network.",
        2019,
        [("users", 4200), ("revenue_range", "gt_250k"), ("funding_range", "1m_5m")],
        ["Senior backend engineer", "Head of sales"],
    ),
    (
        "Fatima Bello",
        "fatima@demo.test",
        "NG",
        "Kano",
        "Founder at Dala Health",
        (
            "Dala Health",
            "healthtech",
            "seed",
            "Remote antenatal care for women in northern Nigeria.",
        ),
        ["healthcare", "community-building"],
        "Dala Health pairs community midwives with a simple phone app and monitoring kits so "
        "pregnant women can get antenatal checks near home. Referral to hospitals is automatic "
        "when a risk sign appears.",
        2022,
        [("users", 6400), ("funding_range", "250k_1m"), ("award", "Aga Khan Foundation grant")],
        ["Clinical operations lead"],
    ),
    (
        "Kofi Asante",
        "kofi@demo.test",
        "GH",
        "Accra",
        "Founder at Sika Escrow",
        (
            "Sika Escrow",
            "fintech",
            "pre-seed",
            "Safe payments for online buyers and sellers in Ghana.",
        ),
        ["payments", "regulation-compliance"],
        "Sika Escrow holds a buyer's money until the goods arrive, so people can trade on "
        "Instagram and WhatsApp without fear of fraud.",
        2024,
        [("users", 1500), ("milestone", "Licensed as a payment service provider")],
        [],
    ),
    (
        "Naledi Dlamini",
        "naledi@demo.test",
        "ZA",
        "Johannesburg",
        "CEO at Ubuntu Learn",
        ("Ubuntu Learn", "edtech", "series-a", "Maths and science tutoring for grades 8 to 12."),
        ["education", "product-management"],
        "Ubuntu Learn combines recorded lessons with live tutor sessions in all eleven "
        "languages of instruction. Used by 120 schools; matric pass rates in partner schools "
        "rose 11 points.",
        2019,
        [("users", 48000), ("revenue_range", "gt_250k"), ("funding_range", "1m_5m")],
        ["Curriculum designer", "Customer success manager"],
    ),
    (
        "Amara Okonkwo",
        "amara@demo.test",
        "NG",
        "Enugu",
        "Founder at Plantain & Co",
        (
            "Plantain & Co",
            "food-beverage",
            "bootstrapped-profitable",
            "Plantain chips and flour sold across West Africa.",
        ),
        ["manufacturing", "sales"],
        "Plantain & Co processes plantain from 300 farmers into chips, flour and baby cereal. "
        "Profitable since year two and stocked in 900 stores.",
        2018,
        [("revenue_range", "gt_250k"), ("milestone", "Stocked in 900 stores")],
        ["Production supervisor"],
    ),
    (
        "Moussa Traoré",
        "moussa@demo.test",
        "SN",
        "Dakar",
        "CTO at Wari Cash",
        ("Wari Cash", "fintech", "seed", "Agent banking software for mobile money agents."),
        ["software-engineering", "cybersecurity"],
        "Wari Cash gives mobile money agents a single app to manage float, commissions and "
        "reconciliation across every network. 2,800 agents in Senegal and Côte d'Ivoire.",
        2021,
        [("users", 2800), ("revenue_range", "50k_250k")],
        ["Security engineer"],
    ),
    (
        "Rehema Juma",
        "rehema@demo.test",
        "TZ",
        "Dar es Salaam",
        "Founder at Safari Stays",
        (
            "Safari Stays",
            "travel",
            "seed",
            "Verified local guesthouses and guides across Tanzania.",
        ),
        ["marketing", "partnerships"],
        "Safari Stays lists small family-run guesthouses and guides that big booking sites "
        "miss, with fair prices and direct payment to hosts.",
        2022,
        [
            ("users", 3100),
            ("revenue_range", "10k_50k"),
            ("award", "Tanzania Tourism innovation prize"),
        ],
        ["Community manager"],
    ),
    (
        "Ibrahim Sesay",
        "ibrahim@demo.test",
        "SL",
        "Freetown",
        "Founder at SolPump",
        ("SolPump", "cleantech", "pre-seed", "Solar water pumps for smallholder irrigation."),
        ["operations", "manufacturing"],
        "SolPump assembles low-cost solar pumps that let a farmer irrigate two hectares in the "
        "dry season. Sold on six-month payment plans.",
        2023,
        [("users", 380), ("milestone", "First 100 pumps installed")],
        [],
    ),
    (
        "Lindiwe Moyo",
        "lindiwe@demo.test",
        "ZW",
        "Harare",
        "Founder at Kuvaka",
        ("Kuvaka", "proptech", "idea", "Affordable housing finance for the diaspora."),
        ["finance", "strategy"],
        "Kuvaka helps people abroad build homes in Zimbabwe in stages, with milestone-based "
        "payments to vetted builders and photo proof of each stage.",
        2025,
        [("milestone", "Waitlist of 600 diaspora families")],
        [],
    ),
    (
        "Yasmin El-Sayed",
        "yasmin@demo.test",
        "EG",
        "Cairo",
        "CEO at Hakim AI",
        ("Hakim AI", "ai-ml", "seed", "Arabic and French voice assistants for customer support."),
        ["machine-learning", "data-science"],
        "Hakim AI builds voice agents that handle customer support calls in Egyptian Arabic, "
        "Darija and West African French. Deployed with two telcos and a bank.",
        2022,
        [
            ("milestone", "Live with 3 enterprise customers"),
            ("revenue_range", "50k_250k"),
            ("partner", "Orange Egypt"),
        ],
        ["ML engineer", "Solutions engineer"],
    ),
    (
        "Emmanuel Nkurunziza",
        "emmanuel@demo.test",
        "RW",
        "Kigali",
        "Founder at Drone Delivery Rwanda",
        (
            "Skyline Medical",
            "logistics",
            "series-a",
            "Drone delivery of blood and vaccines to rural clinics.",
        ),
        ["operations", "regulation-compliance"],
        "Skyline Medical flies blood, vaccines and lab samples to remote clinics in under an "
        "hour. We have completed over 40,000 deliveries with the Rwandan health ministry.",
        2018,
        [("users", 40000), ("funding_range", "gt_5m"), ("partner", "Rwanda Ministry of Health")],
        ["Flight operations lead"],
    ),
    (
        "Hawa Camara",
        "hawa@demo.test",
        "CI",
        "Abidjan",
        "Founder at Griot Studio",
        ("Griot Studio", "media", "pre-seed", "African stories as audio dramas for commuters."),
        ["content-creation", "community-building"],
        "Griot Studio produces serialised audio dramas in French, Wolof and Dioula, funded by "
        "subscriptions and telco bundles.",
        2024,
        [("users", 5200), ("milestone", "1 million episode plays")],
        [],
    ),
]

POSTS = [
    (
        "yetunde@demo.test",
        "win",
        "We just crossed 2,000 traders on Cowrie Books. Twelve months ago it was a spreadsheet and three friends.",
    ),
    (
        "amaka@demo.test",
        "question",
        "For those selling to restaurants: how do you handle payment terms? We are being asked for 30 days and our farmers need paying in 2.",
    ),
    (
        "seun@demo.test",
        "update",
        "Rida Freight now has trucks running the Lagos to Kano corridor with live tracking. The pilot cut average delivery time by a day and a half.",
    ),
    (
        "naledi@demo.test",
        "resource",
        "Our one page template for running a pilot with a school. Scope, success measures, who does what. Steal it.",
    ),
    (
        "fatima@demo.test",
        "opportunity",
        "Dala Health is looking for a clinical operations lead in Kano. Midwife or public health background. Message me.",
    ),
    (
        "tunde@demo.test",
        "update",
        "Seed rounds in African fintech are taking about 5 months to close this year. Plan your runway for at least 9.",
    ),
    (
        "wanjiru@demo.test",
        "win",
        "Signed our first national miller on a 12 month contract. Thanks to everyone who introduced us.",
    ),
    (
        "emmanuel@demo.test",
        "update",
        "40,000 deliveries completed. The biggest lesson: regulators are partners if you bring them in early.",
    ),
    (
        "zanele@demo.test",
        "question",
        "What are you using for customer support in WhatsApp-first markets? We outgrew a shared phone.",
    ),
    (
        "yasmin@demo.test",
        "resource",
        "A list of 40 open Arabic speech datasets we found useful when training voice models.",
    ),
    (
        "kofi@demo.test",
        "update",
        "Received our payment service provider licence from the Bank of Ghana. It took 11 months and I would do it again.",
    ),
    (
        "amara@demo.test",
        "win",
        "Plantain & Co is now stocked in 900 stores. Still profitable. Still bootstrapped.",
    ),
    (
        "ngozi@demo.test",
        "opportunity",
        "Paylane is hiring a Python backend engineer. Remote across Africa, real ownership, small team.",
    ),
    (
        "hawa@demo.test",
        "update",
        "One million plays on Griot Studio this month. People love hearing stories in their own language.",
    ),
    (
        "jide@demo.test",
        "question",
        "Anyone worked with wholesalers on credit? Looking for a fair way to share default risk.",
    ),
    (
        "rehema@demo.test",
        "win",
        "Safari Stays won the Tanzania Tourism innovation prize. Our hosts were on stage with us.",
    ),
]

COMMENTS = [
    (1, "ngozi@demo.test", "Huge. What was the biggest driver of the growth?"),
    (1, "amaka@demo.test", "Congratulations, this is the kind of progress that compounds."),
    (1, "tunde@demo.test", "Send me your deck when you are ready to raise."),
    (
        2,
        "jide@demo.test",
        "We offered 7 days with a small discount for same day payment. Most took the discount.",
    ),
    (
        2,
        "wanjiru@demo.test",
        "Invoice financing worked for us. A partner bank pays the farmers and waits for the restaurant.",
    ),
    (
        2,
        "seun@demo.test",
        "Ask for a deposit on the first three orders, then relax terms as trust builds.",
    ),
    (
        3,
        "tunde@demo.test",
        "A day and a half is a strong result. Which segments are you targeting next?",
    ),
    (3, "wanjiru@demo.test", "We would love to talk. Moving grain from Eldoret is a headache."),
    (4, "funmi@demo.test", "Thank you, this is exactly what we needed for our school pilots."),
    (4, "chidi@demo.test", "Used it for a clinic pilot, worked perfectly."),
    (5, "chidi@demo.test", "Sharing with my network in Kano."),
    (6, "yetunde@demo.test", "Useful and a little scary. Thanks for the honesty."),
    (6, "kofi@demo.test", "Matches what I am seeing. Nine months it is."),
    (
        6,
        "samuel@demo.test",
        "Would also add: start talking to investors before you need the money.",
    ),
    (7, "amaka@demo.test", "Brilliant. Would love to hear how you structured it."),
    (7, "amara@demo.test", "Congratulations, millers are tough customers."),
    (
        8,
        "kwame@demo.test",
        "Inspiring. Most of our regulatory fights could have been avoided with this approach.",
    ),
    (8, "fatima@demo.test", "This is the model for health logistics everywhere."),
    (
        9,
        "ngozi@demo.test",
        "We moved to a shared inbox with WhatsApp Business API. Not perfect but it scaled.",
    ),
    (9, "yasmin@demo.test", "We build voice and chat agents for this. Happy to share how."),
    (10, "funmi@demo.test", "Saving this for our Yoruba model work."),
    (11, "moussa@demo.test", "Eleven months is fast for Ghana. Well done."),
    (11, "yetunde@demo.test", "Any tips on the application? We are starting soon."),
    (12, "aisha@demo.test", "Bootstrapped and profitable is the dream. Congratulations!"),
    (12, "jide@demo.test", "Stocked in 900 stores is serious distribution."),
    (13, "chidi@demo.test", "Applied, thanks for the post."),
    (14, "rehema@demo.test", "Wonderful. I listen on my commute every day."),
    (15, "seun@demo.test", "We share default risk 50-50 with a cap. Happy to walk you through it."),
    (15, "amaka@demo.test", "Insurance backed by sales history worked for us."),
    (16, "aisha@demo.test", "Well deserved. Please say hi to your hosts."),
    (16, "kofi@demo.test", "Congratulations!"),
]

REACTIONS = {
    1: ["ngozi", "amaka", "tunde", "jide", "chidi", "wanjiru"],
    2: ["jide", "seun"],
    3: ["tunde", "wanjiru", "amaka", "yasmin"],
    4: ["funmi", "chidi", "kwame", "aisha"],
    5: ["chidi"],
    6: ["yetunde", "kofi", "samuel", "amaka", "jide"],
    7: ["amaka", "amara", "seun", "tunde"],
    8: ["kwame", "fatima", "tunde", "zanele", "chidi"],
    9: ["ngozi", "yasmin"],
    10: ["funmi", "moussa"],
    11: ["moussa", "yetunde", "tunde"],
    12: ["aisha", "jide", "amaka", "wanjiru", "kofi"],
    13: ["chidi"],
    14: ["rehema", "yetunde"],
    15: ["seun", "amaka"],
    16: ["aisha", "kofi", "yetunde", "hawa", "amara"],
}
REACTION_KINDS = ["like", "celebrate", "insightful"]

YT = "https://www.youtube.com/watch?v="
# Every video here is a public Y Combinator Startup School talk (ids checked against YouTube).
COURSES = [
    {
        "title": "Startup School: from idea to first customers",
        "category": "Foundations",
        "level": "beginner",
        "instructor": "Y Combinator Startup School",
        "description": (
            "<p>A guided path through Y Combinator's Startup School talks. Decide whether to "
            "start, find an idea worth building, talk to users, ship a first version and win "
            "your first customers.</p><p>You will finish with a validated idea, a plan for a "
            "first version and a list of people to sell to.</p>"
        ),
        "modules": [
            (
                "Decide and choose an idea",
                "<p>By the end of this module you will know whether starting up is right for you "
                "now, and how to judge an idea.</p><ul><li>Weigh the trade-offs of starting</li>"
                "<li>Spot and test startup ideas</li></ul>",
                [
                    ("Should you start a startup?", "BUE-icVYRFU"),
                    ("How to get and evaluate startup ideas", "Th8JoIan4dg"),
                ],
            ),
            (
                "Talk to users and build",
                "<p>Learn to run honest conversations with users and ship the smallest product "
                "that teaches you something.</p><ul><li>Ask questions that reveal real needs</li>"
                "<li>Scope a minimum viable product</li></ul>",
                [
                    ("How to talk to users", "z1iF1c8w5Lg"),
                    ("How to build an MVP", "QRZ_l7cVzzU"),
                ],
            ),
            (
                "Launch and win customers",
                "<p>Take your product public and find the first people who will pay for it.</p>"
                "<ul><li>Launch with a clear message</li><li>Find and close first customers</li></ul>",
                [
                    ("The best way to launch your startup", "u36A-YTxiOw"),
                    ("How to get your first customers", "hyYCn_kAngI"),
                ],
            ),
        ],
    },
    {
        "title": "Founders, money and business models",
        "category": "Funding",
        "level": "intermediate",
        "instructor": "Y Combinator Startup School",
        "description": (
            "<p>Build a strong founding team, choose a business model and price, and understand "
            "how fundraising works before you meet an investor.</p>"
        ),
        "modules": [
            (
                "The founding team",
                "<p>Co-founder relationships make or break a startup. Learn what makes them last "
                "and what technical founders should focus on.</p>",
                [
                    ("Keys to successful co-founder relationships", "A4SLDQDXdp0"),
                    ("Tips for technical startup founders", "rP7bpYsfa6Q"),
                ],
            ),
            (
                "Money",
                "<p>Pick a business model, set prices and learn how a funding round works from "
                "first conversation to closing.</p>",
                [
                    ("Startup business models and pricing", "oWZbWzAyHAE"),
                    ("How startup fundraising works", "zBUhQPPS9AY"),
                ],
            ),
        ],
    },
]

ENROLMENTS = [
    # member, course index, how many lessons finished
    ("amaka@demo.test", 0, 4),
    ("ngozi@demo.test", 0, 2),
    ("funmi@demo.test", 0, 6),
    ("yetunde@demo.test", 0, 1),
    ("tunde@demo.test", 1, 4),
    ("kofi@demo.test", 1, 2),
]

EVENTS = [
    ("workshop", "Customer discovery in a week", 4, "Lagos, Nigeria"),
    ("meetup", "Founders breakfast, Accra", 9, "Accra, Ghana"),
    ("workshop", "Pricing your product", 12, "Online"),
    ("demo_day", "Demo Day, Nairobi", 28, "Nairobi, Kenya"),
    ("meetup", "Women in tech evening, Johannesburg", 17, "Johannesburg, South Africa"),
    ("workshop", "Legal basics for startups", 33, "Online"),
]

NEWS = [
    ("Rida Freight closes a Series A", "funding"),
    ("Skyline Medical reaches 40,000 deliveries", "award"),
    ("Sika Escrow gets its payment licence", "announcement"),
    ("Five members named in the Forbes Africa 30 under 30 list", "award"),
    ("New mentor cohort opens for applications", "announcement"),
    ("Delta Capital launches a $10M follow-on fund", "funding"),
]


def make_user(email: str) -> User:
    user = User.objects.create_user(email, PASSWORD)
    user.status = UserStatus.ACTIVE
    user.email_verified_at = timezone.now()
    user.approved_at = timezone.now()
    user.save()
    UserRole.objects.get_or_create(user=user, role="member")
    return user


def traction_items(rows: list[tuple[str, object]]) -> list[dict]:
    return [{"kind": k, "value": v, "visibility": "members"} for k, v in rows]


def fill_startup(
    user: User, description: str, year: int, traction: list, website_slug: str
) -> None:
    startup = Startup.objects.get(owner=user)
    startups.update_startup(
        user_id=user.pk,
        startup_id=startup.pk,
        data={
            "description": description,
            "year_founded": year,
            "website_url": f"https://{website_slug}.example",
            "pitch_deck_url": f"https://{website_slug}.example/pitch-deck",
        },
        if_match=etag_for(startup),
    )
    startup.refresh_from_db()
    startups.replace_traction(
        user_id=user.pk,
        startup_id=startup.pk,
        items=traction_items(traction),
        if_match=etag_for(startup),
    )


def post_jobs(user: User, roles: list[str], startup: Startup) -> None:
    for title in roles:
        jobs.create_job(
            user_id=user.pk,
            data={
                "title": title,
                "type": "full_time",
                "location": f"{startup.city}, {startup.country}",
                "remote": "engineer" in title.lower() or "analyst" in title.lower(),
                "startup_id": startup.pk,
                "description": (
                    f"<p>{startup.name} is hiring a {title.lower()}. You will work directly "
                    "with the founders and own your area from day one.</p>"
                ),
                "apply_method": "email",
                "apply_target": f"careers@{startup.slug.rsplit('-', 1)[0]}.example",
            },
            admin=False,
        )


def main() -> None:
    if not User.objects.filter(email="amaka@demo.test").exists():
        sys.exit("Run scripts/seed_demo.py first.")

    admin = User.objects.get(email="admin@demo.test")
    board = JobSettings.load()
    board.require_approval = False
    board.save()
    known_skills = {s.slug for s in reference.skills()}
    people: dict[str, User] = {
        u.email.split("@")[0]: u for u in User.objects.filter(email__endswith="@demo.test")
    }

    fresh = not User.objects.filter(email=MARKER).exists()
    # Fill in the ten startups from the first seed.
    for email, (description, year, traction, roles) in EXISTING.items():
        if not fresh:
            break
        user = User.objects.get(email=email)
        slug = Startup.objects.get(owner=user).slug.rsplit("-", 1)[0]
        fill_startup(user, description, year, traction, slug)
        post_jobs(user, roles, Startup.objects.get(owner=user))

    # More members and their startups.
    for (
        name,
        email,
        country,
        city,
        headline,
        startup,
        skills,
        description,
        year,
        traction,
        roles,
    ) in MORE:
        if not fresh:
            break
        user = make_user(email)
        people[email.split("@")[0]] = user
        profile = profiles.create_from_signup(
            user.pk, {"full_name": name, "country": country, "city": city}
        )
        profiles.update_profile(
            user_id=user.pk,
            data={
                "headline": headline,
                "bio": f"{name} is building in {city}. Happy to compare notes on what has and has not worked.",
                "skills": [s for s in skills if s in known_skills],
                "open_to": ["partnerships", "mentoring"],
            },
            if_match=etag_for(profile),
        )
        profiles.update_visibility(user_id=user.pk, levels={"basics": "public", "bio": "public"})
        s_name, sector, stage, pitch = startup
        created = startups.create_startup(
            owner_id=user.pk,
            data={
                "name": s_name,
                "country": country,
                "city": city,
                "sector": sector,
                "stage": stage,
                "pitch": pitch[:160],
            },
        )
        startups.update_startup(
            user_id=user.pk,
            startup_id=created.pk,
            data={"directory_opt_in": True},
            if_match=etag_for(created),
        )
        created.refresh_from_db()
        fill_startup(user, description, year, traction, created.slug.rsplit("-", 1)[0])
        post_jobs(user, roles, created)

    # Posts, comments and reactions.
    made = []
    if Post.objects.filter(body_text__startswith=POSTS[0][2][:40]).exists():
        made = list(Post.objects.filter(body_text__in=[p[2] for p in POSTS]))
        by_text = {p.body_text: p for p in made}
        made = [by_text[p[2]] for p in POSTS]
    else:
        for email, category, body in POSTS:
            made.append(
                feed.create_post(
                    user_id=people[email.split("@")[0]].pk,
                    category=category,
                    body=f"<p>{body}</p>",
                    images=[],
                )
            )
        add_activity(made, people)
    follow_each_other(people)
    add_content(admin, people)


def add_activity(made: list, people: dict) -> None:
    for index, email, body in COMMENTS:
        feed.add_comment(
            user_id=people[email.split("@")[0]].pk,
            post_id=made[index - 1].pk,
            body=f"<p>{body}</p>",
        )
    for index, names in REACTIONS.items():
        for n, who in enumerate(names):
            feed.react(
                user_id=people[who].pk,
                target_type="post",
                target_id=made[index - 1].pk,
                kind=REACTION_KINDS[n % 3],
            )


def follow_each_other(people: dict) -> None:
    """Everyone follows a few people, so the following feed has something in it."""
    members = [
        u
        for u in people.values()
        if u.status == UserStatus.ACTIVE
        and u.user_roles.filter(role="member").exists()
        and u.email not in ("admin@demo.test", "editor@demo.test")
    ]
    for i, user in enumerate(members):
        for other in (members[(i + 1) % len(members)], members[(i + 3) % len(members)]):
            if other.pk != user.pk:
                try:
                    follows.follow(viewer=user, kind="member", target_id=other.pk)
                except Exception:  # noqa: BLE001  # a member who cannot be followed is skipped
                    continue


def add_content(admin: User, people: dict) -> None:
    # Events and news.
    now = timezone.now()
    for kind, title, days, where in EVENTS:
        if Event.objects.filter(title=title).exists():
            continue
        event = events.create_event(
            actor=admin,
            data={
                "type": kind,
                "title": title,
                "description": f"<p>{title}. Hear from founders who have done it, ask questions and meet the community.</p>",
                "timezone": "Africa/Lagos",
                "starts_at": now + timedelta(days=days, hours=3),
                "ends_at": now + timedelta(days=days, hours=6),
                "location": where,
                "capacity": 120,
                "public": True,
            },
        )
        events.publish(actor=admin, event_id=event.pk)
    for title, kind in NEWS:
        if EditorialItem.objects.filter(title=title).exists():
            continue
        item = editorial.create_item(
            actor=admin,
            data={
                "type": kind,
                "title": title,
                "body": f"<p>{title}. Read the full story from the WO Community team.</p>",
                "public": True,
                "comments_enabled": True,
            },
        )
        editorial.publish_now(actor=admin, item_id=item.pk)

    # Video courses with modules and an outline for each.
    lesson_ids: list[list] = []
    for spec in COURSES:
        if Course.objects.filter(title=spec["title"]).exists():
            lesson_ids.append([Course.objects.get(title=spec["title"]).pk, []])
            continue
        course = learning.create_course(
            actor=admin,
            data={
                "title": spec["title"],
                "description": spec["description"],
                "instructor": spec["instructor"],
                "category": spec["category"],
                "level": spec["level"],
                "access": "free",
                "open_to_visitors": True,
                "certificate_enabled": True,
            },
        )
        ids = []
        for module_title, outline, videos in spec["modules"]:
            module = learning.add_module(actor=admin, course_id=course.pk, title=module_title)
            learning.add_lesson(
                actor=admin,
                module_id=module.pk,
                data={"type": "reading", "title": "What you will learn", "body": outline},
            )
            for lesson_title, video_id in videos:
                lesson = learning.add_lesson(
                    actor=admin,
                    module_id=module.pk,
                    data={"type": "video", "title": lesson_title, "video_url": YT + video_id},
                )
                ids.append(lesson.pk)
        # Demo courses go live without thumbnails (their cards have a fallback), so they skip the
        # checklist that real courses must pass.
        Course.objects.filter(pk=course.pk).update(status="published", published_at=timezone.now())
        lms.refresh_counts(course.pk)
        lesson_ids.append([course.pk, ids])

    for email, course_index, finished in ENROLMENTS:
        user = people[email.split("@")[0]]
        course_id, _ = lesson_ids[course_index]
        learn.enrol(user_id=user.pk, course_id=course_id)
        ordered = list(
            Lesson.objects.filter(course_id=course_id).order_by("module__position", "position")
        )
        for lesson in ordered[:finished]:
            learn.update_progress(
                user_id=user.pk, lesson_id=lesson.pk, position_seconds=None, completed=True
            )

    print(f"Directory: {directory.reconcile()}")
    print(
        f"Added {len(MORE)} members and startups, {len(POSTS)} posts with comments and reactions,"
    )
    print(f"{len(EVENTS)} events, {len(NEWS)} news stories and {len(COURSES)} video courses.")


if __name__ == "__main__":
    main()
