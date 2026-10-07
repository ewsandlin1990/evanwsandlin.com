#!/usr/bin/env python3
"""Refresh the "Recent reviews" section of more/index.html from a Letterboxd RSS feed.

Usage:
    python3 scripts/update_letterboxd.py              # fetch the live feed
    python3 scripts/update_letterboxd.py --file x.xml # use a saved copy of the feed (for testing)

Only entries with a written review are used (plain diary entries are skipped). Each review is shown in full,
trimmed to about 450 characters if it is very long, with a link to read the rest on Letterboxd.
If anything goes wrong (network error, blocked request, empty feed) the page is left unchanged.
"""
import html, re, sys, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

USERNAME = "evansandlin"
FEED_URL = f"https://letterboxd.com/{USERNAME}/rss/"
REVIEWS_URL = f"https://letterboxd.com/{USERNAME}/films/reviews/"
MAX_REVIEWS = 6
MAX_CHARS = 450
PAGE = Path(__file__).resolve().parent.parent / "more" / "index.html"
START, END = "<!-- LETTERBOXD:START -->", "<!-- LETTERBOXD:END -->"
NS = {"lb": "https://letterboxd.com"}


def load_feed():
    if "--file" in sys.argv:
        return Path(sys.argv[sys.argv.index("--file") + 1]).read_text(encoding="utf-8")
    req = urllib.request.Request(FEED_URL, headers={"User-Agent": "personal-site-updater (evanwsandlin.com)"})
    with urllib.request.urlopen(req, timeout=30) as r:      # raises on 403/429/etc. -> page untouched
        return r.read().decode("utf-8")


def stars(rating):
    """3.5 -> '★★★½'"""
    n = float(rating)
    return "★" * int(n) + ("½" if n % 1 else "")


def review_text(description):
    """Return the written review as plain text, or '' if the entry has none."""
    paras = [html.unescape(re.sub(r"<[^>]+>", "", p)).strip() for p in re.findall(r"<p>(.*?)</p>", description, flags=re.S)]
    paras = [p for p in paras if p and not p.startswith("Watched on")]
    return " ".join(paras)


def films(feed_xml):
    out = []
    for item in ET.fromstring(feed_xml).iter("item"):
        title = item.findtext("lb:filmTitle", namespaces=NS)
        if not title:                                         # skip lists and other non-film entries
            continue
        description = item.findtext("description") or ""
        review = review_text(description)
        if not review:                                        # skip diary entries with no written review
            continue
        poster = re.search(r'<img src="([^"]+)"', description)
        rating = item.findtext("lb:memberRating", namespaces=NS)
        out.append({
            "title": title,
            "year": item.findtext("lb:filmYear", namespaces=NS) or "",
            "rating": stars(rating) if rating else "",
            "date": item.findtext("lb:watchedDate", namespaces=NS),
            "link": item.findtext("link"),
            "poster": poster.group(1) if poster else "",
            "review": review,
        })
    out.sort(key=lambda f: f["date"] or "", reverse=True)    # newest watch date first
    return out[:MAX_REVIEWS]


def trim(text):
    if len(text) <= MAX_CHARS:
        return text, False
    return text[:MAX_CHARS].rsplit(" ", 1)[0].rstrip(",;:.\u2014- ") + "\u2026", True


def render(items):
    e = html.escape
    blocks = []
    for f in items:
        pretty = datetime.strptime(f["date"], "%Y-%m-%d").strftime("%b %-d, %Y") if f["date"] else ""
        head = f'{e(f["title"])}' + (f' <span class="film-year">{e(f["year"])}</span>' if f["year"] else "")
        meta = " \u00b7 ".join(x for x in (f["rating"], pretty) if x)
        alt = f'Poster for {f["title"]}' + (f' ({f["year"]})' if f["year"] else "")
        img = (f'<a class="poster" href="{e(f["link"])}"><img src="{e(f["poster"])}" alt="{e(alt)}" '
               f'width="90" height="135" loading="lazy"></a>') if f["poster"] else ""
        text, cut = trim(f["review"])
        more = f' <a href="{e(f["link"])}">Read on Letterboxd</a>' if cut else ""
        blocks.append(
            f'          <li class="review">{img}<div>'
            f'<p class="film-title"><a href="{e(f["link"])}">{head}</a></p>'
            f'<p class="film-meta">{e(meta)}</p>'
            f'<p class="review-text">{e(text)}{more}</p></div></li>'
        )
    return (f'{START}\n        <ul class="reviews">\n' + "\n".join(blocks) +
            f'\n        </ul>\n        <p class="film-more"><a href="{REVIEWS_URL}">All reviews on Letterboxd</a></p>\n        {END}')


def main():
    items = films(load_feed())
    if not items:
        sys.exit("No films found in the feed; leaving the page unchanged.")
    page = PAGE.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(page):
        sys.exit("Markers not found in more/index.html; leaving the page unchanged.")
    new_page = pattern.sub(lambda m: render(items), page)
    if new_page == page:
        print("No change.")
        return
    PAGE.write_text(new_page, encoding="utf-8")
    print(f"Updated {len(items)} films.")


if __name__ == "__main__":
    main()
