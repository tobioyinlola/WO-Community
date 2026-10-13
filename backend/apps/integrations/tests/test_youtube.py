import pytest

from apps.integrations import youtube

ID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/watch?v={ID}",
        f"https://youtube.com/watch?v={ID}",
        f"https://m.youtube.com/watch?v={ID}",
        f"https://www.youtube.com/watch?v={ID}&t=42s&list=PL123",
        f"https://youtu.be/{ID}",
        f"https://youtu.be/{ID}?t=10",
        f"https://www.youtube.com/embed/{ID}",
        f"https://www.youtube.com/shorts/{ID}",
        f"https://www.youtube.com/live/{ID}",
        f"https://www.youtube.com/v/{ID}",
        f"  https://www.youtube.com/watch?v={ID}  ",
        f"https://WWW.YouTube.com/watch?v={ID}",
        f"https://www.youtube.com:443/watch?v={ID}",
    ],
)
def test_real_video_addresses_are_normalised(url):
    video = youtube.parse(url)
    assert video.video_id == ID
    assert video.url == f"https://www.youtube.com/watch?v={ID}"
    assert video.embed_url == f"https://www.youtube-nocookie.com/embed/{ID}"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "not a link",
        f"http://www.youtube.com/watch?v={ID}",  # not https
        f"https://vimeo.com/{ID}",
        f"https://evil.example.com/watch?v={ID}",
        f"https://youtube.com.evil.example.com/watch?v={ID}",
        f"https://evilyoutube.com/watch?v={ID}",
        f"https://www.youtube.com.evil.example/watch?v={ID}",
        f"https://user:pw@www.youtube.com/watch?v={ID}",
        f"https://www.youtube.com@evil.example.com/watch?v={ID}",
        f"https://www.youtube.com:8443/watch?v={ID}",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/watch?v=",
        "https://www.youtube.com/watch?v=tooshort",
        f"https://www.youtube.com/watch?v={ID}x",
        "https://www.youtube.com/watch?v=<script>alert(1)",
        "https://www.youtube.com/playlist?list=PL1234567890A",
        "https://www.youtube.com/channel/UC1234567890123456789012",
        "https://www.youtube.com/@somechannel",
        f"https://www.youtube.com/embed/{ID}/extra",
        f"https://youtu.be/{ID}/extra",
        "https://youtu.be/",
        f"javascript:alert('{ID}')",
        f"data:text/html,https://www.youtube.com/watch?v={ID}",
        f"https://www.youtube.com/watch?v={ID}\x00",
        "https://www.youtube.com/watch?v=" + "a" * 400,
    ],
)
def test_anything_else_is_refused(url):
    with pytest.raises(youtube.InvalidVideoUrl):
        youtube.parse(url)


def test_the_embed_address_uses_the_privacy_enhanced_host():
    assert youtube.embed_url(ID) == f"https://www.youtube-nocookie.com/embed/{ID}"
