"""Endpoint 2: titles two given actors both appeared in."""
from __future__ import annotations


def test_shared_titles(client):
    r = client.get(
        "/v1/titles/co-starring",
        params={"actor1": "nm0000005", "actor2": "nm0000006"},
    )
    assert r.status_code == 200
    body = r.json()
    # tt0000001 and tt0000005 -- tt0000002 too (both acted in it).
    assert {i["tconst"] for i in body["items"]} == {"tt0000001", "tt0000002", "tt0000005"}
    assert body["total"] == 3


def test_duplicate_principals_row_is_not_double_counted(client):
    """nm0000005 has two `actor` rows on tt0000005 in the fixture."""
    body = client.get(
        "/v1/titles/co-starring",
        params={"actor1": "nm0000005", "actor2": "nm0000006"},
    ).json()
    tconsts = [i["tconst"] for i in body["items"]]
    assert tconsts.count("tt0000005") == 1


def test_self_credits_are_not_acting_credits(client):
    """Both actors have a `self` row on tt0000009; it must not match."""
    body = client.get(
        "/v1/titles/co-starring",
        params={"actor1": "nm0000005", "actor2": "nm0000006"},
    ).json()
    assert "tt0000009" not in {i["tconst"] for i in body["items"]}


def test_argument_order_does_not_matter(client):
    a = client.get(
        "/v1/titles/co-starring", params={"actor1": "nm0000005", "actor2": "nm0000007"}
    ).json()
    b = client.get(
        "/v1/titles/co-starring", params={"actor1": "nm0000007", "actor2": "nm0000005"}
    ).json()
    assert a == b


def test_no_overlap_returns_empty(client):
    body = client.get(
        "/v1/titles/co-starring", params={"actor1": "nm0000006", "actor2": "nm0000007"}
    ).json()
    assert body["total"] == 0
    assert body["items"] == []


def test_person_with_no_acting_credits(client):
    """nm0000008 is a director only -- valid nconst, empty postings list."""
    body = client.get(
        "/v1/titles/co-starring", params={"actor1": "nm0000005", "actor2": "nm0000008"}
    ).json()
    assert body["total"] == 0


def test_unknown_nconst_is_404(client):
    r = client.get(
        "/v1/titles/co-starring", params={"actor1": "nm0000005", "actor2": "nm9999999"}
    )
    assert r.status_code == 404


def test_same_actor_twice_is_400(client):
    r = client.get(
        "/v1/titles/co-starring", params={"actor1": "nm0000005", "actor2": "nm0000005"}
    )
    assert r.status_code == 400


def test_malformed_nconst_is_422(client):
    r = client.get(
        "/v1/titles/co-starring", params={"actor1": "not-an-id", "actor2": "nm0000005"}
    )
    assert r.status_code == 422


def test_results_are_paginated_and_sorted(client):
    body = client.get(
        "/v1/titles/co-starring",
        params={"actor1": "nm0000005", "actor2": "nm0000006", "pageSize": 2, "page": 1},
    ).json()
    assert len(body["items"]) == 2
    assert body["total"] == 3
    page2 = client.get(
        "/v1/titles/co-starring",
        params={"actor1": "nm0000005", "actor2": "nm0000006", "pageSize": 2, "page": 2},
    ).json()
    assert len(page2["items"]) == 1
    all_ids = [i["tconst"] for i in body["items"]] + [i["tconst"] for i in page2["items"]]
    assert all_ids == sorted(all_ids)
