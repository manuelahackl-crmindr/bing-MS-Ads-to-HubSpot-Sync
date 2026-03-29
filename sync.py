import os
import re
import csv
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


def load_report_rows(csv_path: str):
    rows = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "CampaignId": str(row.get("CampaignId", "")).strip(),
                "CampaignName": str(row.get("CampaignName", "")).strip(),
                "Impressions": str(row.get("Impressions", "")).strip(),
                "Clicks": str(row.get("Clicks", "")).strip(),
                "Spend": str(row.get("Spend", "")).strip(),
                "Status": str(row.get("Status", "Active")).strip() or "Active",
            })
    return rows


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

report_rows = load_report_rows("msads_report.csv")

for report_row in report_rows:
    msads_id = report_row["CampaignId"]
    clean_name = sanitize_campaign_name(report_row["CampaignName"])
    match = campaigns_by_msads_id.get(msads_id)

    if not msads_id:
        print("SKIP: missing CampaignId")
        continue

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
