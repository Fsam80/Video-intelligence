def test_health_endpoint_returns_ok(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "Video Intelligence API"


def test_index_page(client) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "Video Intelligence" in r.text
