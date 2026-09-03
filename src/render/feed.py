"""RSS 2.0 feed of incidents, for newsroom data desks to subscribe to."""

from __future__ import annotations

import time
from pathlib import Path
from xml.sax.saxutils import escape

SITE = "https://example.github.io/maritime-watch"


def _rfc822(iso: str) -> str:
    try:
        t = time.strptime(iso.split(".")[0].replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
        return time.strftime("%a, %d %b %Y %H:%M:%S +0000", t)
    except Exception:
        return time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())


def build_feed(store, out_dir: str, site: str = SITE) -> None:
    items = []
    for inc in sorted(store.active_incidents(), key=lambda i: i.last_update, reverse=True)[:60]:
        title = f"[{inc.status}] {inc.type}, {inc.area or 'konum belirsiz'}"
        desc = [f"Güven: {inc.confidence}", f"Önem: {inc.severity}"]
        if inc.casualties:
            desc.append(f"Bildirilen kişi: {inc.casualties}")
        for s in inc.sources:
            desc.append(f"{s.kind}/{s.org or ''}: {s.detail}".strip())
        link = next((s.url for s in inc.sources if s.url), site)
        items.append(
            "    <item>\n"
            f"      <title>{escape(title)}</title>\n"
            f"      <link>{escape(link or site)}</link>\n"
            f'      <guid isPermaLink="false">{escape(inc.id)}-{len(inc.sources)}</guid>\n'
            f"      <pubDate>{_rfc822(inc.last_update)}</pubDate>\n"
            f"      <description>{escape(' | '.join(desc))}</description>\n"
            "    </item>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>\n'
        "  <title>Maritime Watch: Turkiye deniz olaylari</title>\n"
        f"  <link>{escape(site)}</link>\n"
        "  <description>AIS anomalileri + resmi açıklamalar füzyonu. "
        "Doğrulanmamış sinyaller etiketlidir.</description>\n"
        f"  <lastBuildDate>{_rfc822(time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))}</lastBuildDate>\n"
        + "\n".join(items)
        + "\n</channel></rss>\n"
    )
    (Path(out_dir) / "feed.xml").write_text(xml, encoding="utf-8")
