from src.model import (
    CpaEvent,
    Incident,
    IncidentType,
    MarineSafetyRating,
    Source,
    StraitStatus,
    Vessel,
    Warning,
    WeatherContext,
    make_id,
    type_tr,
)


def test_incident_roundtrip():
    inc = Incident(id="x", type="drift", lat=41.0, lon=29.0,
                   vessel=Vessel(name="A", mmsi=1), sources=[Source(kind="ais-anomaly", detail="d")])
    again = Incident.from_dict(inc.to_dict())
    assert again.vessel.mmsi == 1
    assert again.sources[0].kind == "ais-anomaly"
    assert again.to_dict() == inc.to_dict()


def test_incident_track_roundtrip():
    inc = Incident(id="trk", lat=40.5, lon=28.5, track=[[40.4, 28.4], [40.5, 28.5]])
    d = inc.to_dict()
    assert d["track"] == [[40.4, 28.4], [40.5, 28.5]]
    again = Incident.from_dict(d)
    assert again.track == [[40.4, 28.4], [40.5, 28.5]]


def test_tc_mod_01_weather_context_roundtrip():
    wc = WeatherContext(
        wind_kn=22.4,
        gust_kn=29.1,
        wave_m=1.4,
        wind_dir=35,
        beaufort=6,
        summary_tr="29 kn Poyraz ve 1.4m dalga",
        summary_en="29 kn NE gale and 1.4m waves",
        station_name="İstanbul Boğazı",
        distance_nm=3.2,
    )
    d = wc.to_dict()
    again = WeatherContext.from_dict(d)
    assert again == wc
    assert again.wind_kn == 22.4
    assert again.wave_m == 1.4
    assert again.station_name == "İstanbul Boğazı"


def test_tc_mod_02_strait_status_model():
    st = StraitStatus(
        id="bosphorus",
        name="İstanbul Boğazı",
        status="suspended",
        status_tr="Geçiş Askıya Alındı",
        reason="Yoğun Sis (Görüş < 300m)",
        active_vessels_in_transit=4,
        avg_speed_kn=2.1,
    )
    d = st.to_dict()
    assert d["id"] == "bosphorus"
    assert d["status"] == "suspended"
    assert d["status"] in {"open", "caution", "suspended"}
    again = StraitStatus.from_dict(d)
    assert again.id == "bosphorus"
    assert again.active_vessels_in_transit == 4


def test_tc_mod_03_marine_safety_rating_model():
    msr = MarineSafetyRating(
        area="Saroz Körfezi",
        score=28,
        status="danger",
        wave_m=2.3,
        wind_kn=26.5,
        gust_kn=34.0,
        recommendation_tr="Denize çıkmayın!",
        recommendation_en="Do not sail!",
    )
    d = msr.to_dict()
    assert d["score"] == 28
    assert d["status"] in {"good", "caution", "danger"}
    again = MarineSafetyRating.from_dict(d)
    assert again.score == 28
    assert again.status == "danger"


def test_tc_mod_04_cpa_event_model():
    cpa = CpaEvent(
        mmsi1=271001234,
        mmsi2=271005678,
        cpa_nm=0.18,
        tcpa_min=4.2,
        lat=40.85,
        lon=28.90,
        sog1_kn=14.2,
        sog2_kn=12.0,
        vessel1_name="Cargo Alpha",
        vessel2_name="Tanker Beta",
    )
    d = cpa.to_dict()
    assert d["cpa_nm"] == 0.18
    assert d["tcpa_min"] == 4.2
    again = CpaEvent.from_dict(d)
    assert again.mmsi1 == 271001234
    assert again.vessel1_name == "Cargo Alpha"


def test_tc_mod_05_incident_missing_and_new_fields():
    # Empty dict should safely resolve defaults without crashing
    inc_empty = Incident.from_dict({})
    assert inc_empty.id == "unknown"
    assert inc_empty.track == []
    assert inc_empty.heading is None
    assert inc_empty.vessel_type == "unknown"
    assert inc_empty.weather_context is None

    # Incident with weather context and heading
    wc = WeatherContext(
        wind_kn=15.0, gust_kn=20.0, wave_m=0.8, wind_dir=180, beaufort=4,
        summary_tr="15 kn Lodos", summary_en="15 kn S breeze"
    )
    inc = Incident(
        id="cpa-test",
        type=IncidentType.COLLISION_RISK.value,
        heading=225.0,
        vessel_type="tanker",
        weather_context=wc,
    )
    d = inc.to_dict()
    assert d["heading"] == 225.0
    assert d["vessel_type"] == "tanker"
    assert d["weather_context"]["wind_kn"] == 15.0

    again = Incident.from_dict(d)
    assert again.heading == 225.0
    assert again.vessel_type == "tanker"
    assert isinstance(again.weather_context, WeatherContext)
    assert again.weather_context.wind_kn == 15.0
    assert type_tr("collision-risk") == "çatışma riski (yakın geçiş)"


def test_warning_roundtrip():
    w = Warning(id="w", headline="h", area="Marmara Denizi", lat=40.7, lon=28.3)
    assert Warning.from_dict(w.to_dict()).to_dict() == w.to_dict()


def test_add_source_dedupes():
    inc = Incident(id="x")
    a = Source(kind="official", org="SG", detail="tekne battı")
    b = Source(kind="official", org="SG", detail="tekne battı")
    assert inc.add_source(a) is True
    assert inc.add_source(b) is False
    assert len(inc.sources) == 1


def test_make_id_stable_per_day():
    i1 = make_id("ais", 41.005, 29.004, "2026-09-03T09:00:00Z")
    i2 = make_id("ais", 41.006, 29.003, "2026-09-03T23:00:00Z")
    assert i1 == i2  # same rounded position, same day
