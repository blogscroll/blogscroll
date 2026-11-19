#!/usr/bin/env python3
"""BlogScroll site submissions: parse the issue form, check it, and add approved sites.

  site_submission.py check    Post or update the "Submission check" comment and set a check:* label.
  site_submission.py approve  Add every open site request labeled "approved" to its list.toml.

`check` reads the issue from $GITHUB_EVENT_PATH. `approve` reads the current issues from the API.
Issue text is untrusted: it is parsed as data and never passed to a shell.
Standard library only, so there is nothing to install.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
CATEGORIES_DIR = ROOT / "web" / "data" / "categories"
BLOCKLIST = ROOT / ".github" / "site-check" / "blocklist.txt"

BOT_LOGIN = "github-actions[bot]"
APPROVED = "approved"
COMMENT_MARKER = "<!-- blogscroll-site-check"
LABELS = {
    "check:clean": ("0e8a16", "Automated submission check found no problems"),
    "check:review": ("fbca04", "Automated submission check found something to look at"),
    "check:likely-spam": ("b60205", "Automated submission check found strong spam signals"),
}
USER_AGENT = "BlogScroll submission check (+https://blogscroll.com)"
PAGE_BYTES, FEED_BYTES = 1_000_000, 5_000_000
SOCKET_TIMEOUT, FETCH_DEADLINE = 5, 15

# Shared hosts where the registration date of the parent domain says nothing about the site.
SHARED_HOSTS = (
    "github.io", "gitlab.io", "codeberg.page", "neocities.org", "netlify.app", "vercel.app",
    "pages.dev", "substack.com", "medium.com", "wordpress.com", "blogspot.com", "bearblog.dev",
    "micro.blog", "tumblr.com", "ghost.io", "hashnode.dev", "dev.to", "write.as", "srht.site",
)
TWO_LEVEL_SUFFIXES = ("co.uk", "org.uk", "me.uk", "com.au", "net.au", "co.nz", "co.jp", "com.br", "co.za", "co.in")
WATCH_TLDS = {"xyz", "top", "click", "shop", "online", "site", "icu", "buzz", "live", "store", "vip",
              "win", "loan", "bid", "club", "monster", "rest", "sbs", "cfd", "quest"}
SPAM_WORDS = ("casino", "betting", "poker", "loans?", "forex", "crypto", "cbd", "essays?", "escorts?",
              "viagra", "backlinks?", "seo", "marketing agency", "followers", "porn", "replica", "payday")
SPAM_PHRASES = ("write for us", "guest post", "sponsored post", "submit a guest", "buy backlinks",
                "accept guest", "paid post", "link insertion")


# ---------------------------------------------------------------- form parsing and validation

FIELDS = {
    "Site name": "name",
    "Site URL": "url",
    "Favicon URL": "favicon",
    "RSS Feed URL": "feed",
    "Site category": "category",
    "Additional notes": "notes",
}


def parse_form(body: str) -> dict[str, str]:
    """Return the issue form fields by key. Missing or '_No response_' fields are ''."""
    out = {key: "" for key in FIELDS.values()}
    for section in re.split(r"^### ", body or "", flags=re.M)[1:]:
        heading, _, value = section.partition("\n")
        key = FIELDS.get(heading.strip())
        if key:
            value = value.strip()
            out[key] = "" if value == "_No response_" else value
    return out


def categories() -> list[str]:
    return sorted(p.name for p in CATEGORIES_DIR.iterdir() if (p / "list.toml").is_file())


def site_host(host: str) -> str:
    """The host as BlogScroll compares sites: lowercase, without a leading www."""
    return host.lower().removeprefix("www.")


@dataclass
class Submission:
    name: str = ""
    url: str = ""
    host: str = ""
    favicon: str = ""
    feed: str = ""
    category: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return re.sub(r"[^a-z0-9]", "", site_host(self.host))

    def fingerprint(self) -> str:
        """Identifies exactly what was checked, so approval can refuse anything that changed."""
        data = [self.name, self.url, self.favicon, self.feed, self.category]
        return hashlib.sha256(json.dumps(data).encode()).hexdigest()[:16]


def check_https_url(value: str, what: str, errors: list[str]) -> str:
    """Return the host of a public-looking https URL, or '' and add an error."""
    if not value:
        errors.append(f"{what} is empty.")
        return ""
    if len(value) > 300 or not re.fullmatch(r"[\x21-\x7e]+", value):
        errors.append(f"{what} must be at most 300 plain ASCII characters with no spaces.")
        return ""
    try:
        parts = urllib.parse.urlsplit(value)
        port = parts.port
    except ValueError:
        errors.append(f"{what} is not a valid URL.")
        return ""
    host = (parts.hostname or "").lower()
    problem = None
    if parts.scheme != "https":
        problem = "must start with https://"
    elif parts.username or parts.password:
        problem = "must not contain a user name or password"
    elif port not in (None, 443):
        problem = "must not use a custom port"
    elif not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", host):
        problem = "must use a domain name"
    if problem:
        errors.append(f"{what} {problem}.")
        return ""
    return host


def validate(form: dict[str, str], category_override: str = "") -> Submission:
    s = Submission(errors=[])
    s.name = form["name"].strip()
    if not s.name or len(s.name) > 80 or re.search(r"[\x00-\x1f\x7f\ud800-\udfff]", s.name):
        s.errors.append("Site name must be 1 to 80 characters on one line.")
    s.url = form["url"].strip()
    s.host = check_https_url(s.url, "Site URL", s.errors)
    s.favicon = form["favicon"].strip()
    check_https_url(s.favicon, "Favicon URL", s.errors)
    s.feed = form["feed"].strip()
    if s.feed:
        check_https_url(s.feed, "RSS feed URL", s.errors)
    known = categories()
    s.category = category_override or form["category"].strip()
    if s.category not in known:
        s.errors.append(
            f"Category must be one of: {', '.join(known)}. For 'Other', add a `category:<name>` label."
        )
    return s


def category_from_labels(issue: dict) -> str:
    for label in issue.get("labels", []):
        if label.get("name", "").startswith("category:"):
            return label["name"].removeprefix("category:")
    return ""


def submission_of(issue: dict) -> Submission:
    return validate(parse_form(issue.get("body") or ""), category_from_labels(issue))


# ---------------------------------------------------------------- the data files

@dataclass
class Listing:
    hosts: dict[str, str]  # site host -> category
    keys: set[str]
    markers: set[int]      # issue numbers that have a #<issue_N> block

    @classmethod
    def load(cls) -> "Listing":
        listing = cls({}, set(), set())
        for cat in categories():
            text = (CATEGORIES_DIR / cat / "list.toml").read_text(encoding="utf-8")
            listing.markers.update(int(n) for n in re.findall(r"^#<issue_(\d+)>", text, re.M))
            for key, blog in tomllib.loads(text).get("blogs", {}).items():
                listing.keys.add(key)
                host = urllib.parse.urlsplit(blog.get("url", "")).hostname
                if host:
                    listing.hosts[site_host(host)] = cat
        return listing


def toml_string(value: str) -> str:
    """A TOML basic string. JSON escaping is valid TOML for these characters."""
    return json.dumps(value, ensure_ascii=False)


def render_entry(s: Submission, issue_number: int, now: dt.datetime) -> str:
    return (
        f"\n#<issue_{issue_number}>\n"
        f"    [blogs.{s.key}]\n"
        f"    title = {toml_string(s.name)}\n"
        f"    url = {toml_string(s.url)}\n"
        f"    favicon = {toml_string(s.favicon)}\n"
        f"    updated = \"{now.strftime('%Y-%m-%dT%H:%M:%SZ')}\"\n"
        f"#</issue_{issue_number}>\n"
    )


def append_entry(s: Submission, issue_number: int, now: dt.datetime) -> Path:
    """Append the entry, then parse the file again to prove it is valid and correct."""
    path = CATEGORIES_DIR / s.category / "list.toml"
    updated = path.read_text(encoding="utf-8").rstrip("\n") + "\n" + render_entry(s, issue_number, now)
    blog = tomllib.loads(updated)["blogs"].get(s.key, {})
    if (blog.get("title"), blog.get("url"), blog.get("favicon")) != (s.name, s.url, s.favicon):
        raise ValueError("The new entry did not read back with the same values.")
    path.write_text(updated, encoding="utf-8")
    return path


# ---------------------------------------------------------------- network (check only)

def public_ip(host: str) -> str:
    """Resolve host. Every address must be public; return the first one to connect to."""
    infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    ips = [info[4][0] for info in infos]
    if not ips or not all(ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValueError("host does not resolve to public addresses only")
    return ips[0]


class _PinnedHTTPS(http.client.HTTPSConnection):
    """HTTPS to an address that was already checked, so DNS cannot change between check and use."""

    def __init__(self, host: str, ip: str, **kwargs):
        super().__init__(host, **kwargs)
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


@dataclass
class Fetched:
    url: str
    status: int
    content_type: str
    body: bytes


def fetch(url: str, limit: int = PAGE_BYTES, max_redirects: int = 4) -> Fetched:
    """GET a public https URL. Each hop is checked; size and total time are capped."""
    deadline = time.monotonic() + FETCH_DEADLINE
    for _ in range(max_redirects + 1):
        errors: list[str] = []
        host = check_https_url(url, "URL", errors)
        if not host:
            raise ValueError("not an https URL")
        parts = urllib.parse.urlsplit(url)
        conn = _PinnedHTTPS(host, public_ip(host), timeout=SOCKET_TIMEOUT, context=ssl.create_default_context())
        try:
            conn.request("GET", (parts.path or "/") + (f"?{parts.query}" if parts.query else ""),
                         headers={"User-Agent": USER_AGENT, "Accept": "*/*", "Accept-Encoding": "identity"})
            resp = conn.getresponse()
            if resp.status in (301, 302, 303, 307, 308) and resp.getheader("Location"):
                url = urllib.parse.urljoin(url, resp.getheader("Location"))
                continue
            body = b""
            while len(body) < limit and (chunk := resp.read1(min(65536, limit - len(body)))):
                body += chunk
                if time.monotonic() > deadline:
                    raise TimeoutError("fetch took too long")
            return Fetched(url, resp.status, resp.getheader("Content-Type", ""), body)
        finally:
            conn.close()
    raise ValueError("too many redirects")


def registrable_domain(host: str) -> str:
    labels = host.split(".")
    n = 3 if ".".join(labels[-2:]) in TWO_LEVEL_SUFFIXES else 2
    return ".".join(labels[-n:])


def _aware(d: dt.datetime) -> dt.datetime:
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def domain_registered(domain: str) -> dt.datetime | None:
    resp = fetch(f"https://rdap.org/domain/{domain}")
    if resp.status != 200:
        raise LookupError(f"registry returned HTTP {resp.status}")
    for event in json.loads(resp.body or b"{}").get("events", []):
        if event.get("eventAction") == "registration":
            return _aware(dt.datetime.fromisoformat(event["eventDate"].replace("Z", "+00:00")))
    return None


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title, self._in_title, self.feeds = "", False, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "link" and "alternate" in (a.get("rel") or "") and "xml" in (a.get("type") or "") and a.get("href"):
            self.feeds.append(a["href"])

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


@dataclass
class FeedStats:
    items: int
    last_7_days: int
    last_30_days: int
    newest: dt.datetime | None
    oldest: dt.datetime | None
    authors: int


def _parse_date(text: str | None) -> dt.datetime | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return _aware(parsedate_to_datetime(text))
    except (TypeError, ValueError):
        try:
            return _aware(dt.datetime.fromisoformat(text.replace("Z", "+00:00")))
        except ValueError:
            return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def feed_stats(xml: bytes, now: dt.datetime) -> FeedStats:
    root = ElementTree.fromstring(xml)
    items = [el for el in root.iter() if _local(el.tag) in ("item", "entry")]
    dates, authors = [], set()
    for item in items:
        for child in item.iter():
            if _local(child.tag) in ("pubDate", "published", "updated", "date") and (d := _parse_date(child.text)):
                dates.append(d)
                break
        for child in item.iter():
            if _local(child.tag) in ("author", "creator"):
                name = ((child.text or "").strip() or "".join(c.text or "" for c in child)).strip()
                if name:
                    authors.add(name.lower())
    recent = lambda days: sum(1 for d in dates if dt.timedelta(0) <= now - d <= dt.timedelta(days=days))
    return FeedStats(len(items), recent(7), recent(30), max(dates, default=None), min(dates, default=None), len(authors))


# ---------------------------------------------------------------- GitHub API

class GitHub:
    def __init__(self, repo: str, token: str):
        self.repo, self.token = repo, token

    def call(self, method: str, path: str, data: dict | None = None, ok: tuple[int, ...] = ()):
        """Call the REST API. 404 returns None; other statuses in `ok` count as success."""
        url = path if path.startswith("https://") else f"https://api.github.com{path}"
        req = urllib.request.Request(
            url, method=method, data=json.dumps(data).encode() if data is not None else None,
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            if e.code == 404 or e.code in ok:
                return None
            raise

    def pages(self, path: str) -> list:
        out, page = [], 1
        sep = "&" if "?" in path else "?"
        while batch := self.call("GET", f"{path}{sep}per_page=100&page={page}"):
            out += batch
            if len(batch) < 100:
                break
            page += 1
        return out

    def issue(self, n: int) -> dict:
        return self.call("GET", f"/repos/{self.repo}/issues/{n}")

    def comment(self, n: int, body: str):
        self.call("POST", f"/repos/{self.repo}/issues/{n}/comments", {"body": body})

    def remove_label(self, n: int, name: str):
        self.call("DELETE", f"/repos/{self.repo}/issues/{n}/labels/{urllib.parse.quote(name)}")

    def check_comment(self, n: int) -> dict | None:
        return next((c for c in reversed(self.pages(f"/repos/{self.repo}/issues/{n}/comments"))
                     if (c.get("user") or {}).get("login") == BOT_LOGIN and COMMENT_MARKER in c["body"]), None)

    def role(self, login: str) -> str:
        data = self.call("GET", f"/repos/{self.repo}/collaborators/{urllib.parse.quote(login)}/permission") or {}
        return data.get("role_name") or data.get("permission") or "none"


# ---------------------------------------------------------------- the check report

PASS, WARN, FAIL, SKIP = "pass", "warn", "fail", "skip"
ORDER = [SKIP, PASS, WARN, FAIL]
ICON = {PASS: "✅", WARN: "⚠️", FAIL: "❌", SKIP: "➖"}


@dataclass
class Signal:
    name: str
    level: str
    detail: str


def verdict(signals: list[Signal]) -> str:
    fails = sum(s.level == FAIL for s in signals)
    warns = sum(s.level == WARN for s in signals)
    if fails >= 2 or fails * 3 + warns >= 6:
        return "check:likely-spam"
    if fails or warns >= 2:
        return "check:review"
    return "check:clean"


def safe_text(text: str, limit: int = 120) -> str:
    """Text from submitters or sites, made inert for a Markdown comment."""
    text = re.sub(r"\s+", " ", html.unescape(text or "")).strip()[:limit]
    text = text.replace("`", "'").replace("|", "/").replace("@", "@​")
    return f"`{text}`" if text else "(empty)"


def age_text(delta: dt.timedelta) -> str:
    d = delta.days
    return f"{d} days" if d < 120 else f"{d // 30} months" if d < 730 else f"{d // 365} years"


@dataclass
class Context:
    sub: Submission
    login: str
    gh: GitHub
    now: dt.datetime
    listing: Listing
    page: _PageParser = field(default_factory=_PageParser)


def sig_duplicate(c: Context):
    cat = c.listing.hosts.get(site_host(c.sub.host))
    return FAIL if cat else PASS, f"Already listed in `{cat}`." if cat else "Not listed yet."


def sig_blocklist(c: Context):
    lines = BLOCKLIST.read_text().splitlines()
    blocked = {l.strip().lower() for l in lines if l.strip() and not l.startswith("#")}
    hit = c.sub.host in blocked or registrable_domain(c.sub.host) in blocked
    return FAIL if hit else PASS, "Domain is on the blocklist." if hit else "Not on the blocklist."


def sig_name(c: Context):
    text = f"{c.sub.host.replace('.', ' ').replace('-', ' ')} {c.sub.name}".lower()
    words = [m.group(0) for w in SPAM_WORDS if (m := re.search(rf"\b{w}\b", text))]
    tld = c.sub.host.rsplit(".", 1)[-1]
    notes = [f"spam word `{w}`" for w in words] + ([f"`.{tld}` domain"] if tld in WATCH_TLDS else [])
    return WARN if notes else PASS, ", ".join(notes) or "Nothing unusual."


def sig_account(c: Context):
    user = c.gh.call("GET", f"/users/{urllib.parse.quote(c.login)}") or {}
    age = c.now - dt.datetime.fromisoformat(user["created_at"].replace("Z", "+00:00"))
    level = FAIL if age.days < 30 else WARN if age.days < 180 else PASS
    return level, f"Created {age_text(age)} ago, {user.get('public_repos', 0)} public repos."


def sig_history(c: Context):
    q = urllib.parse.quote(f'repo:{c.gh.repo} is:issue author:{c.login} is:closed reason:"not planned"')
    closed = (c.gh.call("GET", f"/search/issues?q={q}&per_page=1") or {}).get("total_count", 0)
    level = FAIL if closed >= 2 else WARN if closed else PASS
    return level, f"{closed} earlier issue(s) closed as not planned." if closed else "None closed as not planned."


def sig_domain_age(c: Context):
    if any(c.sub.host == h or c.sub.host.endswith("." + h) for h in SHARED_HOSTS):
        return SKIP, "Shared host, so the domain age does not apply."
    reg = registrable_domain(c.sub.host)
    created = domain_registered(reg)
    if not created:
        return SKIP, "Registry has no registration date."
    age = c.now - created
    return FAIL if age.days < 90 else WARN if age.days < 365 else PASS, f"`{reg}` registered {age_text(age)} ago."


def sig_home(c: Context):
    home = fetch(c.sub.url)
    if home.status != 200:
        return [Signal("Home page", FAIL, f"Returned HTTP {home.status}.")]
    text = home.body.decode("utf-8", "replace")
    c.page.feed(text)
    final = (urllib.parse.urlsplit(home.url).hostname or "").lower()
    moved = registrable_domain(final) != registrable_domain(c.sub.host)
    lower = text.lower()
    phrases = [p for p in SPAM_PHRASES if p in lower]
    affiliates = len(re.findall(r"[?&](?:tag|ref|aff|affiliate|aff_id)=", lower))
    detail = ", ".join(f"`{p}`" for p in phrases) or "No guest-post or sponsor text."
    return [
        Signal("Home page", WARN if moved else PASS,
               f"Redirects to {safe_text(final)}." if moved else f"Loads. Title: {safe_text(c.page.title)}."),
        Signal("Page content", FAIL if len(phrases) >= 2 else WARN if phrases or affiliates >= 5 else PASS,
               detail + (f" {affiliates} affiliate-style links." if affiliates else "")),
    ]


def sig_favicon(c: Context):
    icon = fetch(c.sub.favicon, limit=200_000)
    ok = icon.status == 200 and ("image" in icon.content_type or "icon" in icon.content_type)
    return PASS if ok else WARN, "Loads." if ok else f"HTTP {icon.status}, type {safe_text(icon.content_type, 40)}."


def sig_feed(c: Context):
    """The strongest signal: content farms post many times a week from many authors."""
    url = c.sub.feed or (urllib.parse.urljoin(c.sub.url, c.page.feeds[0]) if c.page.feeds else "")
    if not url:
        return WARN, "No feed given or found on the home page."
    resp = fetch(url, limit=FEED_BYTES)
    if resp.status != 200:
        return WARN, f"Feed returned HTTP {resp.status}."
    st = feed_stats(resp.body, c.now)
    level = PASS
    notes = [f"{st.items} items", f"{st.last_7_days} in the last 7 days", f"{st.authors or 'no'} named author(s)"]
    if st.last_7_days > 14 or (st.last_7_days > 7 and st.authors >= 3):
        level = FAIL
    elif st.last_7_days > 7 or st.authors >= 5:
        level = WARN
    if st.newest and c.now - st.newest > dt.timedelta(days=365):
        level = max(level, WARN, key=ORDER.index)
        notes.append(f"newest post {age_text(c.now - st.newest)} old")
    if st.oldest and st.items >= 5 and c.now - st.oldest < dt.timedelta(days=60):
        level = max(level, WARN, key=ORDER.index)
        notes.append(f"oldest post only {age_text(c.now - st.oldest)} old")
    return level, ", ".join(notes) + "."


# (name, function, level if the function raises). Order matters: the home page finds the feed link.
SIGNALS: list[tuple[str, Callable, str]] = [
    ("Duplicate", sig_duplicate, SKIP),
    ("Blocklist", sig_blocklist, SKIP),
    ("Name and domain", sig_name, SKIP),
    ("Submitter account", sig_account, SKIP),
    ("Earlier submissions", sig_history, SKIP),
    ("Domain age", sig_domain_age, SKIP),
    ("Home page", sig_home, FAIL),
    ("Favicon", sig_favicon, WARN),
    ("Feed", sig_feed, WARN),
]


def collect_signals(c: Context) -> list[Signal]:
    out = [Signal("Form", FAIL if c.sub.errors else PASS, " ".join(c.sub.errors) or "All fields are valid.")]
    if not c.sub.host:
        return out
    for name, fn, on_error in SIGNALS:
        try:
            result = fn(c)
            out += result if isinstance(result, list) else [Signal(name, *result)]
        except Exception as e:  # noqa: BLE001 - one failed signal must not stop the report
            out.append(Signal(name, on_error, f"Could not check ({type(e).__name__})."))
    return out


def render_report(signals: list[Signal], label: str, fingerprint: str) -> str:
    title = {"check:clean": "✅ No problems found", "check:review": "⚠️ Needs a look",
             "check:likely-spam": "❌ Likely spam"}[label]
    rows = "\n".join(f"| {ICON[s.level]} | {s.name} | {s.detail} |" for s in signals)
    return (
        f"{COMMENT_MARKER} {fingerprint} -->\n### Submission check: {title}\n\n"
        f"| | Signal | Result |\n|---|---|---|\n{rows}\n\n"
        "<sub>Automated and informational only. A maintainer makes the decision. "
        "This check runs again when the issue is edited.</sub>\n"
    )


# ---------------------------------------------------------------- commands

def env_github() -> GitHub:
    return GitHub(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"])


def cmd_check() -> int:
    gh = env_github()
    n = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())["issue"]["number"]
    issue = gh.issue(n)  # current state, not the event payload
    sub = submission_of(issue)
    ctx = Context(sub, issue["user"]["login"], gh, dt.datetime.now(dt.timezone.utc), Listing.load())
    signals = collect_signals(ctx)
    label = verdict(signals)
    report = render_report(signals, label, sub.fingerprint())
    print(report)

    for name, (color, desc) in LABELS.items():
        gh.call("POST", f"/repos/{gh.repo}/labels", {"name": name, "color": color, "description": desc}, ok=(422,))
    for old in LABELS:
        if old != label and any(l["name"] == old for l in issue.get("labels", [])):
            gh.remove_label(n, old)
    gh.call("POST", f"/repos/{gh.repo}/issues/{n}/labels", {"labels": [label]})
    mine = gh.check_comment(n)
    if mine:
        gh.call("PATCH", f"/repos/{gh.repo}/issues/comments/{mine['id']}", {"body": report})
    else:
        gh.comment(n, report)
    return 0


def approval_problem(gh: GitHub, issue: dict, sub: Submission) -> str:
    """Why this approval must not go ahead, or '' if it may."""
    n = issue["number"]
    events = [e for e in gh.pages(f"/repos/{gh.repo}/issues/{n}/events")
              if e.get("event") == "labeled" and (e.get("label") or {}).get("name") == APPROVED]
    if not events:
        return "Could not find who added the label."
    approver = (events[-1].get("actor") or {}).get("login", "")
    if gh.role(approver) not in ("admin", "maintain"):
        return f"{approver} cannot approve sites. That needs the admin or maintain role."
    check = gh.check_comment(n)
    if not check:
        return "There is no submission check yet. Wait for it, then add the label again."
    if f"{COMMENT_MARKER} {sub.fingerprint()} -->" not in check["body"]:
        return "The submission changed after the last check. Read the new check, then add the label again."
    if check["updated_at"] > events[-1]["created_at"]:
        return "The check was updated after the label was added. Read it, then add the label again."
    return ""


def write_output(**values: str):
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
        for key, value in values.items():
            f.write(f"{key}={value}\n")


def cmd_approve() -> int:
    """Add every open, approved site request. Issues to close and the commit message go to $GITHUB_OUTPUT."""
    gh = env_github()
    listing, now = Listing.load(), dt.datetime.now(dt.timezone.utc)
    done, names = [], []
    issues = [i for i in gh.pages(f"/repos/{gh.repo}/issues?state=open&labels={APPROVED}")
              if "pull_request" not in i and "### Site URL" in (i.get("body") or "")]
    for issue in issues:
        n, sub = issue["number"], submission_of(issue)
        if n in listing.markers:  # added by an earlier run that stopped before it closed the issue
            done.append(n)
            continue
        problem = "; ".join(sub.errors) or approval_problem(gh, issue, sub)
        if not problem and site_host(sub.host) in listing.hosts:
            problem = "This site is already listed."
        if not problem and sub.key in listing.keys:
            problem = f"The key `blogs.{sub.key}` is already used."
        if problem:
            gh.comment(n, f"Could not add this site: {problem}")
            gh.remove_label(n, APPROVED)
            print(f"#{n}: {problem}", file=sys.stderr)
            continue
        append_entry(sub, n, now)
        listing.hosts[site_host(sub.host)] = sub.category
        listing.keys.add(sub.key)
        done.append(n)
        names.append(re.sub(r"[#@\n\r]", "", sub.name))
        print(f"#{n}: added blogs.{sub.key} to {sub.category}")
    message = f"Add {', '.join(names)}"[:200] if names else ""
    write_output(issues=" ".join(map(str, done)), message=message)
    return 0


if __name__ == "__main__":
    if sys.version_info < (3, 11):
        sys.exit("Python 3.11 or later is required (tomllib).")
    commands = {"check": cmd_check, "approve": cmd_approve}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit(__doc__)
    sys.exit(commands[sys.argv[1]]())
