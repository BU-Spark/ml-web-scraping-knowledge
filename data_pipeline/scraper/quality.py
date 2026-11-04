"""Quality gates: decide whether a cleaned page is usable, and if not, say why.

Each check returns a reason string when it fails, or None when the page passes.
"""
import re
from urllib.parse import urlsplit

from data_pipeline.scraper import config

PAYWALL_PHRASES = [
    "subscribe to continue reading", "subscribe to read", "to continue reading",
    "sign in to continue", "log in to continue", "login to continue", "sign in to read",
    "create a free account to", "register to continue", "this content is for members",
    "already a subscriber", "become a member to", "unlock this article", "for subscribers only",
    "access this content", "gartner clients",
]
LOGIN_URL_HINTS = re.compile(r"/(login|log-in|signin|sign-in|sso|auth|account/login|users/sign_in)\b", re.I)
JS_WALL_PHRASES = ["enable javascript", "javascript is required", "javascript is disabled",
                   "you need to enable javascript", "please turn on javascript"]
BOT_CHALLENGE_PHRASES = ["just a moment...", "cf-chl", "challenge-platform", "attention required! | cloudflare",
                         "verify you are human", "are you a robot", "captcha", "px-captcha",
                         "access denied", "request unsuccessful. incapsula"]
EN_STOPWORDS = set("the and of to a in is that for it on with as are be this by or an from at you your "
                   "can will not have more their they we our".split())


def word_count(text):
    return len(text.split())


def bot_challenge(http_status, html_lower):
    if http_status not in (200, 403, 429, 503):
        return None
    if http_status == 200 and len(html_lower) > 20000:
        return None  # a full page that merely mentions "captcha" is a real article
    hits = [p for p in BOT_CHALLENGE_PHRASES if p in html_lower]
    return f"bot challenge page ({hits[0]!r})" if hits else None


def paywall_or_login(final_url, original_url, html_lower, words):
    if LOGIN_URL_HINTS.search(final_url or "") and not LOGIN_URL_HINTS.search(original_url):
        return f"redirected to login page {final_url}"
    if words < config.PAYWALL_MAX_WORDS:
        hits = [p for p in PAYWALL_PHRASES if p in html_lower]
        if hits:
            return f"paywall/login phrase {hits[0]!r} with only {words} words"
        if 'type="password"' in html_lower and words < config.MIN_WORDS * 2:
            return f"login form with only {words} words"
    return None


def js_wall(html_lower, words):
    if words >= config.MIN_WORDS:
        return None
    if any(p in html_lower for p in JS_WALL_PHRASES):
        return "page asks to enable JavaScript"
    if re.search(r'<div id="(root|app|__next)"[^>]*>\s*</div>', html_lower):
        return "empty JS app container"
    return None


def non_english(language, text):
    if language and not language.lower().startswith("en"):
        return f"declared language {language}"
    words = re.findall(r"[a-z]+", text.lower()[:5000])
    if len(words) >= 50:
        ratio = sum(w in EN_STOPWORDS for w in words) / len(words)
        if ratio < 0.08:
            return f"few English stopwords ({ratio:.0%})"
    return None


def too_short(words):
    return f"{words} words < {config.MIN_WORDS}" if words < config.MIN_WORDS else None


GENERIC_LAST_SEGMENTS = {"", "resources", "blog", "blogs", "home", "insights", "articles", "news", "index.html"}


def redirected_away(url, final_url):
    """A dead link that redirects to a home/hub page (e.g. a post -> the site's /resources/ page)."""
    if not final_url:
        return None
    orig = [p for p in urlsplit(url).path.split("/") if p]
    final = [p for p in urlsplit(final_url).path.split("/") if p]
    last = final[-1].lower() if final else ""
    if len(final) < len(orig) - 1 and last in GENERIC_LAST_SEGMENTS:
        return f"redirected to generic page {final_url}"
    return None
