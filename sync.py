import os
import re
import requests

HUBSPOT_TOKEN = os.getenv("HUBSPOT_TOKEN")

if not HUBSPOT_TOKEN:
    raise ValueError("Missing HUBSPOT_TOKEN")


def sanitize_campaign_name(name: str) -> str:
    if not name:
        return ""
    cleaned = name.replace("\u00A0", " ")
    cleaned = re.sub(r"[<>()\;+]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:256]


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

if duplicates:
    raise ValueError(f"Duplicate msads_campaign_id values found: {', '.join(duplicates.keys())}")

report_row = {
    "CampaignId": "533348352",
    "CampaignName": "NP  | SN | Köln - Interesse und vor Ort (DACH) + Test",
    "Impressions": "480",
    "Clicks": "19",
    "Spend": "15.99",
    "Status": "Active",
}

msads_id = report_row["CampaignId"]
clean_name = sanitize_campaign_name(report_row["CampaignName"])
match = campaigns_by_msads_id.get(msads_id)

if match:
    payload = {
        "properties": {
            "msads_campaign_id": msads_id,
            "msads_impressions": report_row["Impressions"],
            "msads_clicks": report_row["Clicks"],
            "msads_spend_eur": report_row["Spend"],
            "msads_status": report_row["Status"],
        }
    }

    patch_url = f"https://api.hubapi.com/marketing/v3/campaigns/{match['id']}"
    patch_response = requests.patch(patch_url, headers=headers, json=payload, timeout=30)
    patch_response.raise_for_status()

    updated = patch_response.json()
    print("PATCH OK")
    print(updated["id"])
else:
    payload = {
        "properties": {
            "hs_name": clean_name,
            "hs_notes": "bing",
            "msads_campaign_id": msads_id,
            "msads_impressions": report_row["Impressions"],
            "msads_clicks": report_row["Clicks"],
            "msads_spend_eur": report_row["Spend"],
            "msads_status": report_row["Status"],
        }
    }

    create_url = "https://api.hubapi.com/marketing/v3/campaigns"
    create_response = requests.post(create_url, headers=headers, json=payload, timeout=30)
    create_response.raise_for_status()

    created = create_response.json()
    print("POST OK")
    print(created["id"])
