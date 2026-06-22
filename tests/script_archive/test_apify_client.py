import httpx
import respx

from scripts.archive.apify_client import ApifyClient

BASE = "https://api.apify.com/v2"


@respx.mock
def test_run_hashtag_returns_dataset_items():
    client = ApifyClient(token="tok", poll_interval_seconds=0.0)
    respx.post(f"{BASE}/acts/apidojo~tiktok-scraper/runs").mock(
        return_value=httpx.Response(201, json={"data": {"id": "RUN1"}})
    )
    respx.get(f"{BASE}/actor-runs/RUN1").mock(
        return_value=httpx.Response(
            200, json={"data": {"status": "SUCCEEDED", "defaultDatasetId": "DS1"}}
        )
    )
    respx.get(f"{BASE}/datasets/DS1/items").mock(
        return_value=httpx.Response(200, json=[{"id": "v1"}, {"id": "v2"}])
    )
    items = client.run_hashtag("aisurreal", max_items=2)
    assert [i["id"] for i in items] == ["v1", "v2"]


@respx.mock
def test_run_hashtag_raises_on_failed_status():
    client = ApifyClient(token="tok", poll_interval_seconds=0.0)
    respx.post(f"{BASE}/acts/apidojo~tiktok-scraper/runs").mock(
        return_value=httpx.Response(201, json={"data": {"id": "RUN1"}})
    )
    respx.get(f"{BASE}/actor-runs/RUN1").mock(
        return_value=httpx.Response(200, json={"data": {"status": "FAILED"}})
    )
    try:
        client.run_hashtag("aisurreal", max_items=2)
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
