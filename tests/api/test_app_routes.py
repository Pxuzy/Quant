from __future__ import annotations


def test_data_pipeline_router_is_not_registered(client):
    route_paths = {getattr(route, "path", "") for route in client.app.routes}

    assert not any(path.startswith("/api/data-pipeline") for path in route_paths)
    assert client.get("/api/data-pipeline/status").status_code == 404
