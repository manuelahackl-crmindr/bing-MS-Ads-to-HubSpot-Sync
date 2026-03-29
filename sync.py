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
print(f"Loaded {data.get('total', 0)} campaigns")

results = data.get("results", [])
for campaign in results[:5]:
    campaign_id = campaign.get("id")
    properties = campaign.get("properties", {})
    name = properties.get("hs_name", "")
    msads_id = properties.get("msads_campaign_id", "")
    print(f"- {campaign_id} | {name} | msads_campaign_id={msads_id}")
