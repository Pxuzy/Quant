from __future__ import annotations


def test_watchlist_group_returns_default_group(client):
    response = client.get("/api/watchlist/group")

    assert response.status_code == 200
    assert response.json()["name"] == "default"
    assert isinstance(response.json()["id"], int)
    assert response.json()["created_at"]


def test_watchlist_add_list_reorder_and_delete(client):
    created = client.post(
        "/api/watchlist/items",
        json={"symbol": "sh600519", "note": "availability"},
    )
    assert created.status_code == 201

    listed = client.get("/api/watchlist")
    assert listed.status_code == 200
    assert [item["symbol"] for item in listed.json()] == ["sh600519"]

    reordered = client.put(
        "/api/watchlist/items/reorder",
        json={"symbols": ["sh600519"]},
    )
    assert reordered.status_code == 200
    assert reordered.json() == {"updated": 1}

    deleted = client.delete("/api/watchlist/items/sh600519")
    assert deleted.status_code == 204
    assert client.get("/api/watchlist").json() == []
