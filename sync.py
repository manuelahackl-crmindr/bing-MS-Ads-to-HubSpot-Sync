import os
import requests

HUBSPOT_TOKEN = os.getenv("HUBSPOT_TOKEN")

if not HUBSPOT_TOKEN:
    raise ValueError("Missing HUBSPOT_TOKEN")

url = (
    "https://api.hubapi.com/marketing/v3/campaigns"
    "?limit=100"
    "&properties=hs_name"
    "&properties=msads_campaign_id"
    "&properties=msads_impressions"
    "&properties=msads_clicks"
    "&properties=msads_spend_eur"
    "&properties=msads_status"
)

headers = {
    "Authorization": f"Bearer {HUBSPOT_TOKEN}",
    "Content-Type": "application/json",
}

response = requests.get(url, headers=headers, timeout=30)
response.raise_for_status()

data = response.json()
results = data.get("results", [])

print(f"Loaded {data.get('total', 0)} campaigns")

campaigns_by_msads_id = {}
duplicates = {}

for campaign in results:
    hubspot_campaign_id = campaign.get("id")
    properties = campaign.get("properties", {})
    hs_name = properties.get("hs_name", "")
    msads_campaign_id = properties.get("msads_campaign_id", "")

    if not msads_campaign_id:
        continue

    if msads_campaign_id in campaigns_by_msads_id:
        duplicates.setdefault(msads_campaign_id, []).append({
            "id": hubspot_campaign_id,
            "hs_name": hs_name,
        })
    else:
        campaigns_by_msads_id[msads_campaign_id] = {
            "id": hubspot_campaign_id,
            "hs_name": hs_name,
        }

print(f"Unique Microsoft Ads IDs in HubSpot: {len(campaigns_by_msads_id)}")

if duplicates:
    print("Duplicate msads_campaign_id values found:")
    for msads_id, items in duplicates.items():
        print(f"- {msads_id}")
        first = campaigns_by_msads_id.get(msads_id)
        if first:
            print(f"  - {first['id']} | {first['hs_name']}")
        for item in items:
            print(f"  - {item['id']} | {item['hs_name']}")
else:
    print("No duplicate msads_campaign_id values found")

# Test lookup for one known ID
test_id = "436018748"
match = campaigns_by_msads_id.get(test_id)

if match:
    print(f"Lookup success for {test_id}: {match['id']} | {match['hs_name']}")
else:
    print(f"Lookup failed for {test_id}")
