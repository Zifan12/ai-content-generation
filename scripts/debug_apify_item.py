"""Print one raw Apify TikTok item to verify field names before Blueprint migration.

One-shot debug — run, inspect output, confirm field names match the Phase 1.5
spec assumption (`text`, `videoMeta.coverUrl`, `videoMeta.downloadAddr`,
`authorMeta.name`). Discard after.
"""
import asyncio
import json
import os

from dotenv import load_dotenv
import httpx

load_dotenv("config/.env")

ACTOR_ID = "clockworks~tiktok-hashtag-scraper"
BASE_URL = "https://api.apify.com/v2"


async def main() -> None:
    token = os.getenv("APIFY_API_TOKEN")
    if not token:
        raise SystemExit("APIFY_API_TOKEN missing from config/.env")

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    run_input = {"hashtags": ["viral"], "resultsPerPage": 2}

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:
        run = await client.post(
            f"/acts/{ACTOR_ID}/runs",
            headers=headers,
            json=run_input,
            params={"token": token},
        )
        run.raise_for_status()
        run_id = run.json()["data"]["id"]

        for _ in range(24):
            await asyncio.sleep(5)
            status_resp = await client.get(
                f"/actor-runs/{run_id}",
                headers=headers,
                params={"token": token},
            )
            status_resp.raise_for_status()
            data = status_resp.json()["data"]
            if data["status"] == "SUCCEEDED":
                dataset_id = data["defaultDatasetId"]
                break
            if data["status"] in {"FAILED", "ABORTED", "TIMED-OUT"}:
                raise SystemExit(f"Apify run failed: {data['status']}")
        else:
            raise SystemExit("Apify run did not finish in 120s")

        items_resp = await client.get(
            f"/datasets/{dataset_id}/items",
            headers=headers,
            params={"token": token, "clean": "true"},
        )
        items_resp.raise_for_status()
        items = items_resp.json()

    if not items:
        raise SystemExit("No items returned")

    print(json.dumps(items[0], indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
