"""Download pages politely: one request at a time per host, a delay between them, retries for
temporary errors, and a raw cache so re-running extraction never re-hits a site.

No cookies are kept, nothing logs in, and paywalls/CAPTCHAs/bot challenges are recorded, not bypassed.
"""
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests

from scraper import config


class Throttle:
    """Per-host 'next allowed time'. Different hosts don't wait for each other.

    clock/sleep are injectable so tests can check spacing without real waiting.
    """

    def __init__(self, clock=time.monotonic, sleep=time.sleep):
        self.clock, self.sleep = clock, sleep
        self._next = {}

    def wait(self, host, delay):
        now = self.clock()
        ready = self._next.get(host, now)
        if ready > now:
            self.sleep(ready - now)
        self._next[host] = max(now, ready) + delay


class _NoCookies(requests.cookies.RequestsCookieJar):
    """A cookie jar that never stores anything, so every request is anonymous."""

    def set_cookie(self, *args, **kwargs):
        return None


@dataclass
class FetchResult:
    url: str
    final_url: str = ""
    http_status: int | None = None
    content_type: str = ""          # bare MIME type, e.g. text/html
    headers: dict = field(default_factory=dict)
    error: str = ""                 # set when there was no usable response (timeout, DNS, ...)
    retrieved_at: str = ""
    fetch_method: str = "requests"
    content: bytes = b""

    def meta(self):
        d = asdict(self)
        d.pop("content")
        return d


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _retry_after(resp):
    value = resp.headers.get("Retry-After", "")
    return min(float(value), config.MAX_RETRY_AFTER) if value.isdigit() else None


class Fetcher:
    def __init__(self, session=None, throttle=None, user_agent=None, sleep=time.sleep):
        self.session = session or requests.Session()
        if session is None:
            self.session.cookies = _NoCookies()
        self.session.headers.update({
            "User-Agent": user_agent or config.user_agent(),
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
            "Accept-Language": "en",
        })
        self.throttle = throttle or Throttle()
        self.sleep = sleep
        self.delays = {}  # host -> delay chosen by policy (robots Crawl-delay etc.)

    def _request(self, method, url, delay=None, retries=config.MAX_RETRIES, **kwargs):
        """One polite request with retries for 429/5xx. Returns (response|None, error)."""
        host = urlsplit(url).netloc.lower()
        delay = delay if delay is not None else self.delays.get(host, config.DEFAULT_DELAY)
        error = ""
        for attempt in range(retries + 1):
            self.throttle.wait(host, delay)
            try:
                resp = self.session.request(method, url, timeout=(config.CONNECT_TIMEOUT, config.READ_TIMEOUT),
                                            allow_redirects=True, **kwargs)
            except requests.Timeout:
                error = "timeout"
                resp = None
            except requests.RequestException as err:
                return None, f"{type(err).__name__}: {err}"[:300]
            if resp is not None and resp.status_code != 429 and resp.status_code < 500:
                return resp, ""
            if attempt == retries:
                break
            wait = (_retry_after(resp) if resp is not None else None) or config.BACKOFF_BASE ** (attempt + 1)
            self.sleep(wait)
        return resp, error

    def get_robots(self, robots_url):
        """(status_code|None, text, error) for a robots.txt URL."""
        resp, error = self._request("GET", robots_url)
        if resp is None:
            return None, "", error
        return resp.status_code, resp.text if resp.status_code == 200 else "", ""

    def get(self, url, delay=None):
        result = FetchResult(url=url, retrieved_at=_now())
        resp, error = self._request("GET", url, delay)
        if resp is None:
            result.error = error or "no response"
            return result
        result.final_url = resp.url
        result.http_status = resp.status_code
        result.content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        result.headers = {k: v for k, v in resp.headers.items()
                          if k.lower() in ("content-type", "last-modified", "etag", "content-language", "server")}
        result.content = resp.content
        return result

    def head(self, url, delay=None):
        """Status + content type without downloading the body (falls back to a streamed GET)."""
        result = FetchResult(url=url, retrieved_at=_now())
        resp, error = self._request("HEAD", url, delay, retries=0)
        if resp is None or resp.status_code >= 400:
            # Some servers mishandle HEAD (salesforce.com answers 500); a streamed GET reads only the headers.
            resp, error = self._request("GET", url, delay, stream=True)
            if resp is not None:
                resp.close()
        if resp is None:
            result.error = error or "no response"
            return result
        result.final_url = resp.url
        result.http_status = resp.status_code
        result.content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        return result


# ---- Raw cache: data/output/scrape/raw/<doc_id>.<ext> + <doc_id>.meta.json ----

def _ext(content_type):
    if "pdf" in content_type:
        return "pdf"
    if "html" in content_type or "xml" in content_type or not content_type:
        return "html"
    return "bin"


def save_raw(doc_id, result, extra_meta=None):
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    meta = result.meta() | (extra_meta or {})
    meta["raw_ext"] = _ext(result.content_type)
    if result.content:
        (config.RAW_DIR / f"{doc_id}.{meta['raw_ext']}").write_bytes(result.content)
    (config.RAW_DIR / f"{doc_id}.meta.json").write_text(json.dumps(meta, indent=2))


def load_raw(doc_id):
    """(FetchResult, extra_meta) from the cache, or None if this doc was never fetched."""
    meta_path = config.RAW_DIR / f"{doc_id}.meta.json"
    if not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text())
    known = FetchResult.__dataclass_fields__
    result = FetchResult(**{k: v for k, v in meta.items() if k in known and k != "content"})
    raw_path = config.RAW_DIR / f"{doc_id}.{meta.get('raw_ext', 'html')}"
    if raw_path.exists():
        result.content = raw_path.read_bytes()
    extra = {k: v for k, v in meta.items() if k not in known and k != "raw_ext"}
    return result, extra
