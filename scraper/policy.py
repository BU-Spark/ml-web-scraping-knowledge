"""May we fetch this URL? robots.txt (via Protego) plus the manual rules in domains.yaml.

Conservative by design: if robots.txt can't be read for any reason other than "it doesn't
exist" (404/410), the whole host is treated as blocked.
"""
from dataclasses import dataclass
from urllib.parse import urlsplit

import requests
import yaml
from protego import Protego

from scraper import config


@dataclass
class Decision:
    allowed: bool
    status: str = "allowed"   # allowed | blocked_robots | blocked_tos
    reason: str = ""
    delay: float = config.DEFAULT_DELAY


def load_domain_rules(path=None):
    path = path or config.DOMAINS_FILE
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def rule_for(domain, rules):
    """Most specific matching rule: 'go.forrester.com' matches 'go.forrester.com' or 'forrester.com'."""
    parts = domain.split(".")
    for i in range(len(parts) - 1):
        key = ".".join(parts[i:])
        if key in rules:
            return rules[key] or {}
    return {}


class Policy:
    def __init__(self, fetcher, rules=None):
        self.fetcher = fetcher          # anything with .get_robots(url) -> (status_code|None, text, error)
        self.rules = load_domain_rules() if rules is None else rules
        self._robots = {}               # "https://host" -> (Protego|None, reason)

    def _robots_for(self, url):
        parts = urlsplit(url)
        root = f"{parts.scheme}://{parts.netloc}"
        if root not in self._robots:
            code, text, error = self.fetcher.get_robots(root + "/robots.txt")
            if code == 200:
                self._robots[root] = (Protego.parse(text), "")
            elif code in (404, 410):
                self._robots[root] = (Protego.parse(""), "no robots.txt (allowed)")
            elif code is None:
                self._robots[root] = (None, f"robots.txt unreachable: {error}")
            else:
                self._robots[root] = (None, f"robots.txt returned HTTP {code}")
        return self._robots[root]

    def tos(self, domain):
        """Decision from domains.yaml alone (no network)."""
        rule = rule_for(domain, self.rules)
        if rule.get("skip"):
            return Decision(False, "blocked_tos", rule.get("reason", "skipped in domains.yaml"))
        return Decision(True)

    def tos_flag(self, domain):
        rule = rule_for(domain, self.rules)
        return "skip" if rule.get("skip") else "reviewed" if rule.get("tos_reviewed") else "unreviewed"

    def check(self, url, domain):
        decision = self.tos(domain)
        if not decision.allowed:
            return decision
        rule = rule_for(domain, self.rules)
        robots, note = self._robots_for(url)
        if robots is None:
            return Decision(False, "blocked_robots", note)
        if not robots.can_fetch(url, config.BOT_NAME):
            return Decision(False, "blocked_robots", "disallowed by robots.txt")
        crawl_delay = robots.crawl_delay(config.BOT_NAME) or 0
        delay = max(config.DEFAULT_DELAY, float(crawl_delay), float(rule.get("delay", 0)))
        return Decision(True, "allowed", note, delay)

    def tos_unreviewed(self, domains):
        """Domains nobody has checked the terms of (for the human review list in the report)."""
        out = []
        for d in sorted(set(domains)):
            rule = rule_for(d, self.rules)
            if not rule.get("skip") and not rule.get("tos_reviewed"):
                out.append(d)
        return out
