from src.alert.telegram import Notifier
from src.model import Incident, Source, Vessel, Warning


def _notifier(cfg):
    return Notifier(cfg)


def test_incident_message_has_location_and_links(cfg, capsys):
    n = _notifier(cfg)
    inc = Incident(id="2026-09-04-x", type="distress", status="confirmed",
                   lat=40.90, lon=28.20, area="Marmara Denizi", casualties=2,
                   vessel=Vessel(name="EGE 5", mmsi=271000001))
    inc.sources.append(Source(kind="official", org="Sahil Güvenlik", detail="tekne battı",
                              url="https://sg.gov.tr/x"))
    n.incident(inc, dry=True)

    log = (n.outbox).read_text("utf-8")
    assert "google.com/maps?q=40.9" in log
    assert "example.github.io/maritime-watch/#2026-09-04-x" in log
    assert "marinetraffic.com/en/ais/details/ships/mmsi:271000001" in log
    assert "limanı" in log            # nearest-port line
    assert "EGE 5" in log


def test_sart_always_sends_even_if_status_not_selected(cfg):
    cfg["alert"]["telegram"]["only_status"] = ["confirmed"]
    n = _notifier(cfg)
    inc = Incident(id="sart1", type="distress", status="signal", lat=41.0, lon=29.0)
    inc.sources.append(Source(kind="ais-sart", org="AIS", detail="AIS-SART sinyali alındı"))
    n.incident(inc, dry=True)
    assert "sart1" in "".join(n._sent)


def test_probable_incident_sends(cfg):
    n = _notifier(cfg)
    inc = Incident(id="p1", type="drift", status="probable", lat=41.0, lon=29.0)
    inc.sources.append(Source(kind="ais-anomaly", detail="gap"))
    inc.sources.append(Source(kind="news", org="x", detail="haber"))
    n.incident(inc, dry=True)
    assert "p1" in "".join(n._sent)


def test_warning_message(cfg):
    n = _notifier(cfg)
    w = Warning(id="w1", headline="Marmara: dalga ~2.6 m", area="Marmara Denizi",
                kind="marine-weather", severity="major", org="Open-Meteo", lat=40.7, lon=28.3)
    n.warning(w, dry=True)
    log = n.outbox.read_text("utf-8")
    assert "Denizcilik hava uyarısı" in log
    assert "google.com/maps" in log
