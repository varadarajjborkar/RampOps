"""The static dashboard must satisfy the CSP in vercel.json and reference only files that exist."""
import re
from html.parser import HTMLParser
from pathlib import Path

PUBLIC = Path(__file__).resolve().parent.parent / "public"
HTML = (PUBLIC / "index.html").read_text()


def test_every_local_reference_exists():
    refs = re.findall(r'(?:src|href)="(/[^"#?]*)"', HTML)
    assert refs
    for ref in refs:
        if ref.startswith("/api/"):
            continue
        assert (PUBLIC / ref.lstrip("/")).is_file(), ref


class _Inline(HTMLParser):
    """Collects anything the CSP would block: inline script bodies, <style> blocks, style attributes."""

    def __init__(self):
        super().__init__()
        self.problems = []
        self._script_without_src = False

    def handle_starttag(self, tag, attrs):
        names = dict(attrs)
        if "style" in names:
            self.problems.append(f"style attribute on <{tag}>")
        if tag == "style":
            self.problems.append("<style> block")
        self._script_without_src = tag == "script" and "src" not in names

    def handle_endtag(self, tag):
        self._script_without_src = False

    def handle_data(self, data):
        if self._script_without_src and data.strip():
            self.problems.append("inline script body")


def test_no_inline_script_or_style_in_html():
    # The CSP forbids all of these, so any of them would silently do nothing in production.
    parser = _Inline()
    parser.feed(HTML)
    assert parser.problems == []


def test_no_inline_style_or_third_party_urls_in_scripts_and_css():
    for path in list((PUBLIC / "js").rglob("*.js")) + [PUBLIC / "css" / "styles.css"]:
        text = path.read_text()
        assert "setAttribute(\"style\"" not in text, path
        assert "innerHTML" not in text, f"{path}: use textContent, API data is untrusted"
        assert not re.search(r"https?://(?!www\.w3\.org)", text.replace("http://127", "")), path


def test_modules_only_import_local_files():
    for path in (PUBLIC / "js").rglob("*.js"):
        for target in re.findall(r'from "([^"]+)"', path.read_text()):
            assert target.startswith("."), f"{path}: {target}"
            assert (path.parent / target).resolve().is_file(), f"{path}: {target}"


def test_no_em_dashes_in_shipped_files():
    for path in PUBLIC.rglob("*"):
        if path.is_file() and path.suffix in {".html", ".js", ".css", ".svg"}:
            assert "\u2014" not in path.read_text(), path
