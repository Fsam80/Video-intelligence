"""Detect which platform a URL belongs to.

Order of support decided for the project: TikTok first, then YouTube,
Instagram, and manual file import as the universal fallback.
"""

from urllib.parse import urlparse

PLATFORMS: dict[str, tuple[str, ...]] = {
    "tiktok": ("tiktok.com", "vm.tiktok.com", "vt.tiktok.com"),
    "youtube": ("youtube.com", "youtu.be", "m.youtube.com"),
    "instagram": ("instagram.com",),
    "facebook": ("facebook.com", "fb.watch"),
    "x": ("x.com", "twitter.com"),
}

# Platforms enabled in this version. Others are detected but rejected cleanly.
ENABLED = {"tiktok", "youtube"}


def detect_platform(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    for name, domains in PLATFORMS.items():
        if any(host == d or host.endswith("." + d) for d in domains):
            return name
    return None
