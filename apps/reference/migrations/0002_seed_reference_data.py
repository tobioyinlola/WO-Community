from django.db import migrations

SECTORS = [
    ("Fintech", "fintech"),
    ("Healthtech", "healthtech"),
    ("Edtech", "edtech"),
    ("Agritech", "agritech"),
    ("E-commerce and marketplaces", "ecommerce"),
    ("Logistics and mobility", "logistics"),
    ("Clean energy and cleantech", "cleantech"),
    ("Property and construction", "proptech"),
    ("B2B software", "b2b-software"),
    ("AI and machine learning", "ai-ml"),
    ("Media and entertainment", "media"),
    ("Travel and hospitality", "travel"),
    ("Food and beverage", "food-beverage"),
    ("Fashion and consumer goods", "consumer-goods"),
    ("Creator economy", "creator-economy"),
    ("Gaming", "gaming"),
    ("Cybersecurity", "cybersecurity"),
    ("Hardware and IoT", "hardware-iot"),
    ("Legal and compliance", "legal-compliance"),
    ("Social impact", "social-impact"),
    ("Other", "other"),
]

STAGES = [
    ("Idea", "idea"),
    ("Pre-seed", "pre-seed"),
    ("Seed", "seed"),
    ("Series A", "series-a"),
    ("Series B and later", "series-b-plus"),
    ("Bootstrapped and profitable", "bootstrapped-profitable"),
]

SKILLS = [
    ("Product management", "product-management"),
    ("Software engineering", "software-engineering"),
    ("Mobile development", "mobile-development"),
    ("Data science", "data-science"),
    ("Machine learning", "machine-learning"),
    ("UX and product design", "ux-design"),
    ("Brand and marketing", "marketing"),
    ("Growth", "growth"),
    ("Sales", "sales"),
    ("Business development", "business-development"),
    ("Fundraising", "fundraising"),
    ("Finance", "finance"),
    ("Accounting", "accounting"),
    ("Legal", "legal"),
    ("Operations", "operations"),
    ("Supply chain", "supply-chain"),
    ("Recruiting and HR", "hr-recruiting"),
    ("Customer success", "customer-success"),
    ("Community building", "community-building"),
    ("Content creation", "content-creation"),
    ("Partnerships", "partnerships"),
    ("Strategy", "strategy"),
    ("Public relations", "public-relations"),
    ("Project management", "project-management"),
    ("Cybersecurity", "cybersecurity"),
    ("Cloud and DevOps", "cloud-devops"),
    ("Blockchain", "blockchain"),
    ("Payments", "payments"),
    ("Regulation and compliance", "regulation-compliance"),
    ("Healthcare", "healthcare"),
    ("Agriculture", "agriculture"),
    ("Education", "education"),
    ("Manufacturing", "manufacturing"),
    ("E-commerce", "ecommerce-skill"),
    ("Social media", "social-media"),
    ("Copywriting", "copywriting"),
    ("Analytics", "analytics"),
    ("Negotiation", "negotiation"),
    ("Public speaking", "public-speaking"),
]


def seed(apps, schema_editor):
    for model_name, rows in (("Sector", SECTORS), ("Stage", STAGES), ("Skill", SKILLS)):
        model = apps.get_model("reference", model_name)
        for order, (name, slug) in enumerate(rows):
            model.objects.get_or_create(slug=slug, defaults={"name": name, "sort_order": order})


class Migration(migrations.Migration):
    dependencies = [("reference", "0001_initial")]

    # Rows are left in place on reverse: other tables may point at them.
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
