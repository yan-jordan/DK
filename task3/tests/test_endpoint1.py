


"""Endpoint 1: solo creator who is still alive."""
from __future__ import annotations

EXPECTED = {"tt0000001", "tt0000005", "tt0000008"}


def test_total_matches_hand_computed_set(client):
    r = client.get("/v1/titles/solo-creator", params={"pageSize": 100})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == len(EXPECTED)
    assert {i["tconst"] for i in body["items"]} == EXPECTED


def test_dead_person_excluded(client):
    body = client.get("/v1/titles/solo-creator", params={"pageSize": 100}).json()
    assert "tt0000002" not in {i["tconst"] for i in body["items"]}


def test_unknown_birth_year_excluded(client):
    body = client.get("/v1/titles/solo-creator", params={"pageSize": 100}).json()
    assert "tt0000003" not in {i["tconst"] for i in body["items"]}


def test_implausibly_old_person_excluded(client):
    """No deathYear but born 1830: absence of deathYear is not proof of life."""
    body = client.get("/v1/titles/solo-creator", params={"pageSize": 100}).json()
    assert "tt0000004" not in {i["tconst"] for i in body["items"]}


def test_multi_director_or_multi_writer_excluded(client):
    body = client.get("/v1/titles/solo-creator", params={"pageSize": 100}).json()
    got = {i["tconst"] for i in body["items"]}
    assert "tt0000006" not in got  # two directors, one writer
    assert "tt0000007" not in got  # one director, two writers


def test_quote_in_title_survives_parsing(client):
    """IMDb TSVs are unquoted; a bare `"` must not shift columns."""
    body = client.get("/v1/titles/solo-creator", params={"pageSize": 100}).json()
    titles = {i["tconst"]: i["primaryTitle"] for i in body["items"]}
    assert titles["tt0000005"] == 'The "Quoted" Film'


def test_null_start_year_is_null_not_zero(client):
    body = client.get("/v1/titles/solo-creator", params={"pageSize": 100}).json()
    row = next(i for i in body["items"] if i["tconst"] == "tt0000005")
    assert row["startYear"] is None


def test_person_is_attached(client):
    body = client.get("/v1/titles/solo-creator", params={"pageSize": 100}).json()
    row = next(i for i in body["items"] if i["tconst"] == "tt0000001")
    assert row["person"] == {"nconst": "nm0000001", "primaryName": "Alive Auteur"}


def test_pagination_is_a_partition(client):
    """Pages must tile the result set exactly: no gaps, no repeats."""
    total = client.get("/v1/titles/solo-creator").json()["total"]
    seen = []
    page = 1
    while True:
        body = client.get(
            "/v1/titles/solo-creator", params={"page": page, "pageSize": 2}
        ).json()
        assert body["total"] == total
        if not body["items"]:
            break
        seen.extend(i["tconst"] for i in body["items"])
        page += 1
        assert page < 50, "pagination did not terminate"
    assert len(seen) == total
    assert len(set(seen)) == total
    assert seen == sorted(seen), "page order must be stable"


def test_page_past_the_end_is_empty_not_an_error(client):
    body = client.get("/v1/titles/solo-creator", params={"page": 9999}).json()
    assert body["items"] == []
    assert body["total"] == len(EXPECTED)


def test_page_size_is_bounded(client):
    assert client.get("/v1/titles/solo-creator", params={"pageSize": 100000}).status_code == 422
    assert client.get("/v1/titles/solo-creator", params={"pageSize": 0}).status_code == 422
    assert client.get("/v1/titles/solo-creator", params={"page": 0}).status_code == 422
