"""Reject damaged landing-page images before publication; never rewrite assets."""

import hashlib
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, ImageOps, ImageStat

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


class Images(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.images.append(dict(attrs))


def validate():
    parser = Images()
    parser.feed((SITE / "index.html").read_text())
    assert len(parser.images) == 5, "Unexpected landing-page image count"
    for attrs in parser.images:
        filename = urlsplit(attrs["src"]).path.removeprefix("./")
        asset = SITE / filename
        with Image.open(asset) as source:
            source.load()  # Detect truncated or undecodable files.
            displayed = ImageOps.exif_transpose(source)
            dimensions = (int(attrs["width"]), int(attrs["height"]))
            assert displayed.size == dimensions, (
                f"{filename}: HTML dimensions {dimensions} do not match "
                f"EXIF-oriented image {displayed.size}"
            )
            variance = ImageStat.Stat(displayed.convert("RGB")).stddev
            assert max(variance) > 5, f"{filename}: blank or nearly uniform image"
            if filename == "pix-qr.png":
                assert displayed.width == displayed.height, "PIX QR must be square"
        print(f"PASS {filename}: decoded, nonblank, dimensions {dimensions}")

    # Preserve factual hardware evidence without the conversion that erased pixels.
    for asset, original in [
        ("weather-hardware.jpg", "weather.jpg"),
        ("sysops-hardware.jpg", "sysops.jpg"),
    ]:
        assert (SITE / asset).read_bytes() == (ROOT / "docs/images" / original).read_bytes(), (
            f"{asset}: must preserve the original hardware photograph"
        )
    assert hashlib.sha256((SITE / "pix-qr.png").read_bytes()).hexdigest() == (
        "2f0a57267b9e7d4debfa7bc8186286c2905b74b168c7ac1d1a6ac53a7f60c47b"
    ), "PIX QR differs from the maintainer-confirmed original"
    print("Site images: original photos and confirmed PIX QR preserved.")


if __name__ == "__main__":
    validate()
