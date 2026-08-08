from trendpulse.collectors.eonet import EonetCollector, _in_bbox

CFG = {
    "eonet": {
        "window_days": 30,
        "regions": {
            "gcc_levant": {
                "bbox": [34, 12, 63, 37],
                "category_keywords": {
                    "floods": ["car insurance flood claim uae", "emergency loan uae"],
                },
            },
            "south_asia_corridor": {
                "bbox": [60, 5, 93, 37],
                "category_keywords": {
                    "floods": ["send money to india from uae"],
                },
            },
        },
    },
}

PAYLOAD = {
    "events": [
        {   # Oman flood — inside GCC bbox, mapped category
            "title": "Flood in Oman 1103806",
            "categories": [{"id": "floods", "title": "Floods"}],
            "geometry": [{"type": "Point", "coordinates": [57.5, 21.5],
                          "date": "2026-08-01T00:00:00Z"}],
        },
        {   # Belarus flood — OUT of every bbox (reproduces the API leak)
            "title": "Flood in Belarus 1104065",
            "categories": [{"id": "floods", "title": "Floods"}],
            "geometry": [{"type": "Point", "coordinates": [27.5, 53.5],
                          "date": "2026-07-31T00:00:00Z"}],
        },
        {   # India flood — inside remittance-corridor bbox
            "title": "Flood in India 1104100",
            "categories": [{"id": "floods", "title": "Floods"}],
            "geometry": [{"type": "Point", "coordinates": [77.0, 20.0],
                          "date": "2026-08-05T00:00:00Z"}],
        },
        {   # GCC wildfire — in bbox but category NOT mapped -> ignored
            "title": "Wildfire in Syrian Arab Republic",
            "categories": [{"id": "wildfires", "title": "Wildfires"}],
            "geometry": [{"type": "Point", "coordinates": [37.0, 35.0],
                          "date": "2026-06-22T00:00:00Z"}],
        },
    ],
}


class FakeResponse:
    def json(self):
        return PAYLOAD


def test_in_bbox():
    assert _in_bbox([57.5, 21.5], [34, 12, 63, 37])       # Oman
    assert not _in_bbox([27.5, 53.5], [34, 12, 63, 37])   # Belarus


def test_eonet_client_side_filtering(monkeypatch):
    calls = {}

    def fake_get(url, params=None, timeout=None, retries=None):
        calls["params"] = params
        return FakeResponse()

    monkeypatch.setattr("trendpulse.collectors.eonet.http_get", fake_get)
    obs, discs = EonetCollector(CFG).safe_fetch([])

    assert calls["params"]["days"] == 30

    by_kw = {(o.keyword, o.region): o.value for o in obs}
    # Oman flood -> GCC angles, count 1
    assert by_kw[("car insurance flood claim uae", "gcc_levant")] == 1.0
    assert by_kw[("emergency loan uae", "gcc_levant")] == 1.0
    # India flood -> corridor angle
    assert by_kw[("send money to india from uae", "south_asia_corridor")] == 1.0
    # Belarus leaked event filtered out; unmapped wildfire ignored
    assert all("belarus" not in d.context.lower() for d in discs)
    assert not any("wildfire" in d.context.lower() for d in discs)
    # evidence carries the event title
    oman = [d for d in discs if d.keyword == "car insurance flood claim uae"]
    assert oman and "Flood in Oman" in oman[0].context


def test_eonet_no_regions_is_noop(monkeypatch):
    obs, discs = EonetCollector({"eonet": {}}).safe_fetch([])
    assert obs == [] and discs == []
