from src.process.safety_index import (
    calculate_safety_rating,
    calculate_safety_score,
    evaluate_all_areas,
    score_to_status,
)


def test_tc_saf_01_calm_sea():
    # Hs = 0.4m, Vw = 7.0 kn, Vg = 10.0 kn -> Good
    rating = calculate_safety_rating(
        area="Marmara Denizi",
        wave_m=0.4,
        wind_kn=7.0,
        gust_kn=10.0,
        has_storm_warning=False,
    )
    assert rating.score >= 85
    assert rating.status == "good"
    assert "elverişli" in rating.recommendation_tr.lower()
    assert "favorable" in rating.recommendation_en.lower()


def test_tc_saf_02_moderate_caution():
    # Hs = 1.3m, Vw = 19.0 kn, Vg = 26.0 kn -> Caution
    rating = calculate_safety_rating(
        area="Çanakkale Boğazı",
        wave_m=1.3,
        wind_kn=19.0,
        gust_kn=26.0,
        has_storm_warning=False,
    )
    assert 45 <= rating.score < 75
    assert rating.status == "caution"
    assert "tedbirli" in rating.recommendation_tr.lower() or "çırpıntılı" in rating.recommendation_tr.lower()


def test_tc_saf_03_storm_danger():
    # Hs = 2.8m, Vw = 32.0 kn, Vg = 42.0 kn -> Danger
    rating = calculate_safety_rating(
        area="Saroz Körfezi",
        wave_m=2.8,
        wind_kn=32.0,
        gust_kn=42.0,
        has_storm_warning=False,
    )
    assert rating.score < 45
    assert rating.status == "danger"
    assert "denize çıkmayın" in rating.recommendation_tr.lower()


def test_tc_saf_04_official_storm_warning_penalty():
    # Hs = 0.5m, Vw = 8.0 kn (otherwise calm) BUT has_storm_warning = True
    calm_score = calculate_safety_score(wave_m=0.5, wind_kn=8.0, gust_kn=10.0, has_storm_warning=False)
    assert calm_score == 100

    warn_rating = calculate_safety_rating(
        area="İzmir Körfezi",
        wave_m=0.5,
        wind_kn=8.0,
        gust_kn=10.0,
        has_storm_warning=True,
    )
    # Penalty of 50 should drop score to 50
    assert warn_rating.score == 50
    assert warn_rating.status in {"caution", "danger"}


def test_tc_saf_05_missing_wave_data_graceful():
    # In sheltered inner bays, wave model might be None
    rating = calculate_safety_rating(
        area="İzmit Körfezi",
        wave_m=None,
        wind_kn=22.0,
        gust_kn=28.0,
        has_storm_warning=False,
    )
    assert rating.wave_m is None
    assert isinstance(rating.score, int)
    assert 0 <= rating.score <= 100
    assert rating.status == "caution"


def test_tc_saf_06_edge_cases_and_extremes():
    # Negative wind or extreme gale
    score_negative = calculate_safety_score(wave_m=-0.5, wind_kn=-10.0, gust_kn=-5.0)
    assert score_negative == 100

    score_hurricane = calculate_safety_score(wave_m=12.0, wind_kn=80.0, gust_kn=110.0)
    assert score_hurricane == 0
    assert score_to_status(0) == "danger"


def test_evaluate_all_areas():
    points = [
        {"name": "İstanbul Boğazı", "wave_m": 0.5, "wind_kn": 12.0, "gust_kn": 16.0},
        {"name": "Antalya Körfezi", "wave_m": 2.5, "wind_kn": 30.0, "gust_kn": 40.0},
    ]
    ratings = evaluate_all_areas(points, storm_areas={"Antalya Körfezi"})
    assert len(ratings) == 2
    assert ratings[0].area == "İstanbul Boğazı"
    assert ratings[0].status in {"good", "caution"}
    assert ratings[1].area == "Antalya Körfezi"
    assert ratings[1].status == "danger"
