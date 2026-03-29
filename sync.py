if match:
    print("ACTION = PATCH")
    print(f"HubSpot campaign id: {match['id']}")
    payload = {
        "properties": {
            "msads_campaign_id": msads_id,
            "msads_impressions": report_row["Impressions"],
            "msads_clicks": report_row["Clicks"],
            "msads_spend_eur": report_row["Spend"],
            "msads_status": report_row["Status"],
        }
    }
    print(payload)
else:
    print("ACTION = POST")
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
    print(payload)

    create_url = "https://api.hubapi.com/marketing/v3/campaigns"
    create_response = requests.post(create_url, headers=headers, json=payload, timeout=30)
    create_response.raise_for_status()

    created = create_response.json()
    print("Campaign created successfully")
    print(f"New HubSpot campaign id: {created.get('id')}")
