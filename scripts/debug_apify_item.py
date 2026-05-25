"""
Debug script: inspect raw Apify TikTok response fields.

WHY THIS EXISTS:
  One-shot debug utility. Run to fetch a single TikTok item via Apify actor
  and inspect the raw JSON response. Useful when:
  - Migrating scraper logic (verify field names match assumptions)
  - Debugging missing/malformed fields
  - Confirming API response structure after actor updates

EXPECTED FIELDS (verify presence after run):
  - id: video unique ID
  - text: caption/description
  - videoMeta.coverUrl: thumbnail URL
  - videoMeta.downloadAddr: direct MP4 download URL
  - authorMeta.name: creator username
  - video.duration: length in seconds
  - song.{id, title, artist}: audio metadata
  - hashtags[]: list of hashtag strings
  - stats: {diggCount, shareCount, commentCount, playCount}

USAGE:
  uv run python scripts/debug_apify_item.py
  
  Prints pretty-printed JSON response to stdout. Inspect manually.
  No output is saved; this is diagnostic only.

DISCARD AFTER:
  This is a throwaway debug script. Delete once fields are confirmed.
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
            params={"token": token},  # Apify requires token in query param despite Authorization header; header alone returns 401
        )
        run.raise_for_status()
        run_id = run.json()["data"]["id"]

        # 24 × 5s = 120s max wait; Apify typical run time is 30–60s for small hashtag scrapes
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

    subtitle_links = items[0].get("videoMeta", {}).get("subtitleLinks", [])
    if subtitle_links:
        url = subtitle_links[0].get("downloadLink")
        print("\n--- SUBTITLE FILE ---")
        async with httpx.AsyncClient(timeout=10.0) as sub_client:
            sub_resp = await sub_client.get(url)
            print(sub_resp.text[:800])
    else:
        print("\n--- NO subtitleLinks found ---")


if __name__ == "__main__":
    asyncio.run(main())
