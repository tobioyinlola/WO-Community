import pytest

pytestmark = pytest.mark.django_db

PUBLIC = "/api/v1/public/testimonials"


def test_the_first_testimonials_are_on_the_website_in_order(api_client):
    body = api_client.get(PUBLIC).json()
    assert [t["name"] for t in body] == [
        "Tomiwa Allan Ogunmodede",
        "Linda Obi",
        "Jumoke Oduwole",
        "Sunil Sharma",
        "Isidore Kpotufe",
        "Benaiah Rawlings",
    ]
    assert body[3]["quote"] == (
        "Onyeka is a brilliant mentor of startups from Africa with over 60 startups mentored"
    )
    assert body[3]["role"] == "MD, Techstars Toronto, Canada"
    assert all(len(t["quote"]) <= 400 for t in body)
