import datetime as dt
import re
import sys
import tomllib
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import site_submission as ss  # noqa: E402

NOW = dt.datetime(2026, 11, 18, 12, 0, tzinfo=dt.timezone.utc)

FORM = """### FAQ acknowledgement

- [x] I read the FAQ

### Site name

Jane's "Notes"

### Site URL

https://www.Example.org/blog

### Favicon URL

https://example.org/favicon.ico

### RSS Feed URL

_No response_

### Site category

personal

### Additional notes

Hi
"""


class FormTests(unittest.TestCase):
    def test_parse_reads_fields_and_no_response(self):
        form = ss.parse_form(FORM)
        self.assertEqual(form["name"], 'Jane\'s "Notes"')
        self.assertEqual(form["feed"], "")
        self.assertEqual(form["category"], "personal")

    def test_valid_submission(self):
        s = ss.validate(ss.parse_form(FORM))
        self.assertEqual(s.errors, [])
        self.assertEqual(s.host, "www.example.org")
        self.assertEqual(s.key, "exampleorg")

    def test_rejects_unsafe_urls(self):
        for url in ("http://example.org", "https://user:pw@example.org", "https://example.org:8443",
                    "https://127.0.0.1", "javascript:alert(1)", "https://exa mple.org", ""):
            errors = []
            self.assertEqual(ss.check_https_url(url, "URL", errors), "", url)
            self.assertTrue(errors, url)

    def test_other_category_needs_label(self):
        form = ss.parse_form(FORM.replace("\npersonal\n", '\nOther (please specify in "Additional Notes")\n'))
        self.assertTrue(ss.validate(form).errors)
        self.assertEqual(ss.validate(form, "technology").errors, [])

    def test_rejects_control_and_non_ascii_url_characters(self):
        for url in ("https://example.org/a\x7fb", "https://example.org/\u00e9", "https://example.org/\ud800"):
            errors = []
            self.assertEqual(ss.check_https_url(url, "URL", errors), "", repr(url))

    def test_fingerprint_changes_with_fields(self):
        a = ss.validate(ss.parse_form(FORM))
        b = ss.validate(ss.parse_form(FORM.replace("favicon.ico", "other.ico")))
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_name_on_one_line(self):
        form = ss.parse_form(FORM)
        form["name"] = "a\x1bb"
        self.assertTrue(ss.validate(form).errors)


class DataTests(unittest.TestCase):
    def test_every_list_parses(self):
        for cat in ss.categories():
            tomllib.loads((ss.CATEGORIES_DIR / cat / "list.toml").read_text(encoding="utf-8"))

    def test_listing_loads_hosts_keys_and_markers(self):
        listing = ss.Listing.load()
        self.assertIn("den.dev", listing.hosts)
        self.assertIn("dendev", listing.keys)
        self.assertIn(641, listing.markers)

    def test_append_refuses_entry_that_does_not_read_back(self):
        s = ss.validate(ss.parse_form(FORM))
        s.host = "den.dev"  # key "dendev" already exists, so TOML rejects the duplicate table
        with self.assertRaises(Exception):
            doc = (ss.CATEGORIES_DIR / "technology" / "list.toml").read_text() + ss.render_entry(s, 1, NOW)
            tomllib.loads(doc)

    def test_entry_round_trips_with_quotes_and_backslashes(self):
        s = ss.validate(ss.parse_form(FORM))
        s.name = 'Tricky "name" \\ with = and [brackets]'
        doc = "[blogs]\n" + ss.render_entry(s, 42, NOW)
        blog = tomllib.loads(doc)["blogs"]["exampleorg"]
        self.assertEqual(blog["title"], s.name)
        self.assertEqual(blog["updated"], "2026-11-18T12:00:00Z")
        self.assertIn("#<issue_42>", doc)

    def test_blocklist_is_readable(self):
        lines = [l for l in ss.BLOCKLIST.read_text().splitlines() if l and not l.startswith("#")]
        self.assertTrue(all(l == l.strip().lower() for l in lines))


class SignalTests(unittest.TestCase):
    def test_registrable_domain(self):
        self.assertEqual(ss.registrable_domain("blog.example.co.uk"), "example.co.uk")
        self.assertEqual(ss.registrable_domain("www.example.com"), "example.com")

    def test_verdict(self):
        sig = lambda *levels: [ss.Signal("x", l, "") for l in levels]
        self.assertEqual(ss.verdict(sig(ss.PASS, ss.WARN, ss.SKIP)), "check:clean")
        self.assertEqual(ss.verdict(sig(ss.WARN, ss.WARN)), "check:review")
        self.assertEqual(ss.verdict(sig(ss.FAIL)), "check:review")
        self.assertEqual(ss.verdict(sig(ss.FAIL, ss.FAIL)), "check:likely-spam")

    def test_safe_text_is_inert(self):
        out = ss.safe_text("hi `@team` | <b>x</b>")
        self.assertNotIn("`@", out)
        self.assertNotIn("|", out[1:-1])
        self.assertTrue(out.startswith("`") and out.endswith("`"))

    def test_feed_stats_rss_and_atom(self):
        rss = b"""<rss><channel>
          <item><pubDate>Tue, 17 Nov 2026 10:00:00 GMT</pubDate><author>a</author></item>
          <item><pubDate>Mon, 02 Nov 2026 10:00:00 GMT</pubDate><author>b</author></item>
          <item><pubDate>Mon, 01 Jan 2024 10:00:00 GMT</pubDate></item></channel></rss>"""
        st = ss.feed_stats(rss, NOW)
        self.assertEqual((st.items, st.last_7_days, st.last_30_days, st.authors), (3, 1, 2, 2))
        atom = b"""<feed xmlns="http://www.w3.org/2005/Atom">
          <entry><updated>2026-11-18T08:00:00Z</updated><author><name>Jo</name></author></entry></feed>"""
        st = ss.feed_stats(atom, NOW)
        self.assertEqual((st.items, st.last_7_days, st.authors), (1, 1, 1))

    def test_public_ip_rejects_private_and_metadata_addresses(self):
        for ip in ("10.0.0.5", "127.0.0.1", "169.254.169.254", "::1", "fd00::1"):
            fake = [(None, None, None, None, (ip, 443))]
            with mock.patch.object(ss.socket, "getaddrinfo", return_value=fake):
                with self.assertRaises(ValueError, msg=ip):
                    ss.public_ip("example.com")

    def test_fetch_checks_every_redirect_hop(self):
        class Resp:
            def __init__(self, status, location=None):
                self.status, self._loc = status, location
            def getheader(self, name, default=None):
                return self._loc if name == "Location" else default
            def read1(self, n):
                return b""
        class Conn:
            def __init__(self, host, ip, **kw):
                self.host = host
            def request(self, *a, **kw):
                pass
            def getresponse(self):
                return Resp(302, "https://internal.example/")
            def close(self):
                pass
        def resolve(host):
            if host == "internal.example":
                raise ValueError("private")
            return "93.184.216.34"
        with mock.patch.object(ss, "_PinnedHTTPS", Conn), mock.patch.object(ss, "public_ip", side_effect=resolve):
            with self.assertRaises(ValueError):
                ss.fetch("https://example.com/")

    def test_word_boundaries(self):
        ctx = lambda host, name: ss.Context(ss.Submission(name=name, host=host), "u", None, NOW, None)
        self.assertEqual(ss.sig_name(ctx("seoul-diary.com", "Museo notes"))[0], ss.PASS)
        self.assertEqual(ss.sig_name(ctx("best-seo-tips.com", "x"))[0], ss.WARN)
        self.assertEqual(ss.sig_name(ctx("cheap-loans.xyz", "x"))[0], ss.WARN)

    def test_report_survives_every_signal_failing(self):
        s = ss.validate(ss.parse_form(FORM))
        ctx = ss.Context(s, "u", None, NOW, ss.Listing({}, set(), set()))
        boom = mock.Mock(side_effect=OSError("down"))
        with mock.patch.object(ss, "SIGNALS", [(n, boom, lvl) for n, _, lvl in ss.SIGNALS]):
            signals = ss.collect_signals(ctx)
        self.assertEqual(len(signals), 2 + len(ss.SIGNALS))
        self.assertIn("Could not check", signals[-1].detail)
        self.assertIn(s.fingerprint(), ss.render_report(signals, ss.verdict(signals), s.fingerprint()))


class PolicyTests(unittest.TestCase):
    def test_country_tlds(self):
        for host in ("example.ru", "a.b.cn", "site.su", "пример.рф", "x.xn--p1ai", "news.hk", "blog.by", "site.ir"):
            self.assertTrue(ss.blocked_country(host), host)
        for host in ("example.com", "russia-fan.com", "ru.example.org", "example.io", "cnn.com"):
            self.assertFalse(ss.blocked_country(host), host)

    def test_policy_checks_favicon_and_feed_too(self):
        s = ss.validate(ss.parse_form(FORM))
        self.assertEqual(ss.policy_blocks(s), [])
        s.favicon, s.feed = "https://cdn.example.cn/icon.png", "https://feeds.example.ru/rss"
        self.assertEqual(len(ss.policy_blocks(s)), 2)

    def test_policy_applies_to_invalid_non_ascii_url(self):
        s = ss.validate(ss.parse_form(FORM.replace("https://www.Example.org/blog", "https://пример.рф")))
        self.assertTrue(s.errors)
        self.assertTrue(ss.policy_blocks(s))

    def test_blocklisted_domain_and_subdomain(self):
        self.assertTrue(ss.blocked_domain("www.durablepicks.com"))
        self.assertTrue(ss.blocked_domain("huumanupgrade.blogspot.com"))
        self.assertFalse(ss.blocked_domain("other.blogspot.com"))

    def test_blocked_verdict_wins(self):
        sig = [ss.Signal("Policy", ss.FAIL, "x", True), ss.Signal("Feed", ss.PASS, "")]
        self.assertEqual(ss.verdict(sig), "check:blocked")

    def test_tld_file_is_clean(self):
        entries = ss._list_file(ss.BLOCKED_TLDS)
        self.assertTrue(entries)
        self.assertTrue(all(re.fullmatch(r"[a-z0-9-]+", e) for e in entries), entries)


class FakeGitHub:
    repo = "o/r"

    def __init__(self, role="maintain", check_body=None, check_time="2026-11-18T10:00:00Z",
                 label_time="2026-11-18T11:00:00Z"):
        self._role, self._body, self._ct, self._lt = role, check_body, check_time, label_time

    def pages(self, path):
        return [{"event": "labeled", "label": {"name": "approved"}, "actor": {"login": "den"},
                 "created_at": self._lt}]

    def role(self, login):
        return self._role

    def check_comment(self, n):
        return None if self._body is None else {"body": self._body, "updated_at": self._ct}


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.sub = ss.validate(ss.parse_form(FORM))
        self.issue = {"number": 7}
        self.good = ss.marker_line(self.sub.fingerprint()) + "\n### Submission check"

    def test_maintainer_role_is_accepted(self):
        self.assertEqual(ss.approval_problem(FakeGitHub("maintain", self.good), self.issue, self.sub), "")

    def test_write_role_is_refused(self):
        self.assertIn("cannot approve", ss.approval_problem(FakeGitHub("write", self.good), self.issue, self.sub))

    def test_changed_after_check_is_refused(self):
        stale = f"{ss.COMMENT_MARKER} 0000000000000000 -->"
        self.assertIn("changed", ss.approval_problem(FakeGitHub("admin", stale), self.issue, self.sub))

    def test_check_newer_than_label_is_refused(self):
        gh = FakeGitHub("admin", self.good, check_time="2026-11-18T12:00:00Z")
        self.assertIn("after the label", ss.approval_problem(gh, self.issue, self.sub))

    def test_no_check_is_refused(self):
        self.assertIn("no submission check", ss.approval_problem(FakeGitHub("admin", None), self.issue, self.sub))


BASE_TOML = """[blogs]
    [blogs.dendev]
    title = "Den"
    url = "https://den.dev"
    favicon = "https://den.dev/f.ico"
    updated = "2024-09-01T14:00:00Z"
"""


class FakePRGitHub:
    repo = "blogscroll/blogscroll"

    def __init__(self, head_toml, files=("web/data/categories/technology/list.toml",)):
        self.head_toml, self.files = head_toml, files

    def pages(self, path):
        return [{"filename": f, "status": "modified"} for f in self.files]

    def raw(self, path):
        return self.head_toml


PR = {"number": 5, "user": {"login": "u"}, "head": {"sha": "abc", "repo": {"full_name": "fork/blogscroll"}},
      "base": {"sha": "def"}}
TECH = (ss.CATEGORIES_DIR / "technology" / "list.toml").read_text(encoding="utf-8")
NEW_ENTRY = """
    [blogs.exampleorg]
    title = "Example"
    url = "https://example.org"
    favicon = "https://example.org/f.ico"
    updated = "2026-11-01T00:00:00Z"
"""


class PullRequestTests(unittest.TestCase):
    def entries(self, head, files=("web/data/categories/technology/list.toml",)):
        gh = FakePRGitHub(head, files)
        return ss.pr_entries(gh, PR, gh.pages(""))

    def test_new_and_changed_entries_are_found_against_main(self):
        head = TECH.replace('url = "https://den.dev"', 'url = "https://den.dev/"') + NEW_ENTRY
        found = [(e.key, e.existing) for e in self.entries(head)]
        self.assertEqual(found, [("dendev", True), ("exampleorg", False)])

    def test_unchanged_and_removed_files_are_ignored(self):
        self.assertEqual(self.entries(TECH), [])
        gh = FakePRGitHub(TECH)
        files = [{"filename": "web/data/categories/technology/list.toml", "status": "removed"}]
        self.assertEqual(ss.pr_entries(gh, PR, files), [])

    def test_invalid_toml_is_reported(self):
        entries = self.entries('[blogs]\n  title = "$TS\n')
        self.assertEqual(len(entries), 1)
        self.assertIsNone(entries[0].sub)
        self.assertIn("not valid TOML", entries[0].error)

    def test_pr_without_list_changes_is_skipped(self):
        self.assertIsNone(ss.check_pr(FakePRGitHub(TECH, files=("README.md",)), PR, ss.Listing({}, set(), set()), NOW))

    def test_other_files_fail_and_blocked_entry_wins(self):
        head = TECH + NEW_ENTRY.replace("example.org", "example.ru").replace("exampleorg", "exampleru")
        gh = FakePRGitHub(head, files=("web/data/categories/technology/list.toml", ".github/workflows/x.yml"))
        with mock.patch.object(ss, "SIGNALS", []):
            label, report, signals = ss.check_pr(gh, PR, ss.Listing({}, set(), set()), NOW)
        self.assertEqual(label, "check:blocked")
        self.assertTrue(report.startswith(ss.marker_line("pr:abc") + "\n"))
        self.assertIn("Other files", [s.name for s in signals])

    def test_marker_must_be_the_first_line(self):
        planted = "x\n" + ss.marker_line("pr:abc")
        self.assertFalse(planted.startswith(ss.marker_line("pr:abc") + "\n"))


class FormTemplateTests(unittest.TestCase):
    def test_dropdown_matches_category_folders(self):
        form = (ss.ROOT / ".github" / "ISSUE_TEMPLATE" / "1-site-request.yml").read_text()
        block = form.split("id: site-category", 1)[1].split("options:", 1)[1].split("validations:", 1)[0]
        options = [l.strip()[2:] for l in block.splitlines() if l.strip().startswith("- ")]
        self.assertEqual(sorted(o for o in options if not o.startswith("Other")), ss.categories())


if __name__ == "__main__":
    unittest.main()
