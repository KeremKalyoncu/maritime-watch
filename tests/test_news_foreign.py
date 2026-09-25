"""Far-away accidents are news, not warnings for the Turkish coast."""

from email.utils import formatdate

from src.ingest import news


def _rss(*titles):
    now = formatdate(usegmt=True)
    items = "".join(
        f"<item><title>{t}</title><link>https://example.test/{i}</link><pubDate>{now}</pubDate></item>"
        for i, t in enumerate(titles)
    )
    return f"<rss><channel>{items}</channel></rss>"


def _titles(cfg, monkeypatch, *titles):
    cfg["news"]["feeds"] = ["https://example.test/rss"]
    monkeypatch.setattr(news, "fetch_parallel", lambda tasks, **k: [(_rss(*titles), True)])
    return [i.sources[0].detail for i in news.fetch_news(cfg)]


def test_foreign_ferry_capsize_is_dropped(cfg, monkeypatch):
    out = _titles(
        cfg,
        monkeypatch,
        "Endonezya'da alabora olan feribottaki 52 kişinin cesedine ulaşıldı",
        "Çin'de yolcu teknesi battı: 12 ölü",
    )
    assert out == []


def test_foreign_word_with_turkish_place_is_kept(cfg, monkeypatch):
    out = _titles(
        cfg,
        monkeypatch,
        "İtalya bandıralı gemi Çanakkale Boğazı'nda arızalandı, gemi sürüklendi",
        "Bodrum açıklarında göçmen teknesi battı",
    )
    assert len(out) == 2
