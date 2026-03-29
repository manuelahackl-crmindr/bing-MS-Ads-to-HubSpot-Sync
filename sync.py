import os
import re
import csv
import io
import time
import zipfile
import requests

HUBSPOT_TOKEN = os.getenv("HUBSPOT_TOKEN")
MSADS_CLIENT_ID = os.getenv("MSADS_CLIENT_ID")
MSADS_CLIENT_SECRET = os.getenv("MSADS_CLIENT_SECRET")
MSADS_REFRESH_TOKEN = os.getenv("MSADS_REFRESH_TOKEN")
MSADS_DEVELOPER_TOKEN = os.getenv("MSADS_DEVELOPER_TOKEN")
MSADS_CUSTOMER_ID = os.getenv("MSADS_CUSTOMER_ID")
MSADS_ACCOUNT_ID = os.getenv("MSADS_ACCOUNT_ID")

required = [
    "HUBSPOT_TOKEN",
    "MSADS_CLIENT_ID",
    "MSADS_CLIENT_SECRET",
    "MSADS_REFRESH_TOKEN",
    "MSADS_DEVELOPER_TOKEN",
    "MSADS_CUSTOMER_ID",
    "MSADS_ACCOUNT_ID",
]

missing = [key for key in required if not os.getenv(key)]
if missing:
    raise ValueError(f"Missing env vars: {', '.join(missing)}")


def sanitize_campaign_name(name: str) -> str:
    if not name:
        return ""
    cleaned = name.replace("\u00A0", " ")
    cleaned = re.sub(r"[<>()\;+]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:256]


def refresh_msads_access_token():
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    data = {
        "client_id": MSADS_CLIENT_ID,
        "client_secret": MSADS_CLIENT_SECRET,
        "scope": "https://ads.microsoft.com/msads.manage",
        "refresh_token": MSADS_REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }
    response = requests.post(token_url, data=data, timeout=30)
    response.raise_for_status()
    return response.json()["access_token"]


def submit_report(access_token: str):
    url = "https://reporting.api.bingads.microsoft.com/Reporting/v13/Reports/SubmitGenerateReport"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "DeveloperToken": MSADS_DEVELOPER_TOKEN,
        "CustomerId": str(MSADS_CUSTOMER_ID),
        "AccountId": str(MSADS_ACCOUNT_ID),
        "Content-Type": "application/json",
    }
    body = {
        "ReportRequest": {
            "Type": "CampaignPerformanceReportRequest",
            "Format": "Csv",
            "FormatVersion": "2.0",
            "ReportName": "Microsoft Ads Weekly Campaign Report",
            "ReturnOnlyCompleteData": False,
            "Aggregation": "WeeklyStartingMonday",
            "Columns": [
                "TimePeriod",
                "CampaignId",
                "CampaignName",
                "Impressions",
                "Clicks",
                "Spend",
            ],
            "Scope": {
                "AccountIds": [int(MSADS_ACCOUNT_ID)]
            },
            "Time": {
                "PredefinedTime": "LastWeekStartingMonday",
                "ReportTimeZone": "AmsterdamBerlinBernRomeStockholmVienna",
            },
        }
    }
    response = requests.post(url, headers=headers, json=body, timeout=60)
    response.raise_for_status()
    data = response.json()
    report_request_id = data.get("ReportRequestId") or data.get("reportRequestId")
    if not report_request_id:
        raise ValueError(f"No ReportRequestId found: {data}")
    return report_request_id, headers


def poll_report(report_request_id: str, headers: dict):
    url = "https://reporting.api.bingads.microsoft.com/Reporting/v13/Reports/PollGenerateReport"
    body = {"ReportRequestId": report_request_id}
    response = requests.post(url, headers=headers, json=body, timeout=60)
    response.raise_for_status()
    return response.json()


def download_and_parse_report(download_url: str):
    response = requests.get(download_url, timeout=120)
    response.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        csv_name = zf.namelist()[0]
        with zf.open(csv_name) as f:
            content = f.read().decode("utf-8-sig")

    rows = []
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        rows.append({
            "CampaignId": str(row.get("CampaignId", "")).strip(),
            "CampaignName": str(row.get("CampaignName", "")).strip(),
            "Impressions": str(row.get("Impressions", "")).strip(),
            "Clicks": str(row.get("Clicks", "")).strip(),
            "Spend": str(row.get("Spend", "")).strip(),
            "Status": "Active",
        })
    return rows


def get_hubspot_campaigns():
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
    return response.json(), headers


def build_hubspot_lookup(results):
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

    return campaigns_by_msads_id


def sync_rows(report_rows, campaigns_by_msads_id, hubspot_headers):
    for report_row in report_rows:
        msads_id = report_row["CampaignId"]
        clean_name = sanitize_campaign_name(report_row["CampaignName"])
        match = campaigns_by_msads_id.get(msads_id)

        if not msads_id:
            print("SKIP missing CampaignId")
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
            patch_response = requests.patch(patch_url, headers=hubspot_headers, json=payload, timeout=30)
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
            create_response = requests.post(create_url, headers=hubspot_headers, json=payload, timeout=30)
            create_response.raise_for_status()
            created = create_response.json()
            print("POST OK")
            print(created["id"])


access_token = refresh_msads_access_token()
print("Access token OK")

report_request_id, msads_headers = submit_report(access_token)
print(f"ReportRequestId: {report_request_id}")

download_url = None
for _ in range(12):
    time.sleep(5)
    poll_data = poll_report(report_request_id, msads_headers)
    status = (
        poll_data.get("ReportRequestStatus", {}).get("Status")
        or poll_data.get("reportRequestStatus", {}).get("status")
    )
    print(f"Report status: {status}")
    if status == "Success":
        download_url = (
            poll_data.get("ReportRequestStatus", {}).get("ReportDownloadUrl")
            or poll_data.get("reportRequestStatus", {}).get("reportDownloadUrl")
        )
        break
    if status == "Error":
        raise ValueError(f"Report failed: {poll_data}")

if not download_url:
    raise ValueError("No ReportDownloadUrl found")

report_rows = download_and_parse_report(download_url)
print(f"Downloaded report rows: {len(report_rows)}")

hubspot_data, hubspot_headers = get_hubspot_campaigns()
campaigns_by_msads_id = build_hubspot_lookup(hubspot_data.get("results", []))

sync_rows(report_rows, campaigns_by_msads_id, hubspot_headers)
