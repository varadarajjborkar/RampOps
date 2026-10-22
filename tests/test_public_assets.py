"""The static dashboard must satisfy the CSP in vercel.json and reference only files that exist."""
import re
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


def test_no_inline_script_or_style_in_html():
    # The CSP forbids both, so either would silently do nothing in production.
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>\s*\S", HTML)
    assert "<style" not in HTML
    assert not re.search(r'\sstyle="', HTML)


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
