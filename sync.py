import os
import re
import csv
import io
import time
import zipfile
import requests
import xml.etree.ElementTree as ET

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


def localname(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def extract_first_tag(xml_text: str, tag_name: str):
    root = ET.fromstring(xml_text)
    for elem in root.iter():
        if localname(elem.tag) == tag_name:
            return elem.text
    return None


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
    url = "https://reporting.api.bingads.microsoft.com/Api/Advertiser/Reporting/v13/ReportingService.svc"

    body = f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:i="http://www.w3.org/2001/XMLSchema-instance" xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Header xmlns="https://bingads.microsoft.com/Reporting/v13">
    <Action mustUnderstand="1">SubmitGenerateReport</Action>
    <AuthenticationToken>{access_token}</AuthenticationToken>
    <CustomerAccountId>{MSADS_ACCOUNT_ID}</CustomerAccountId>
    <CustomerId>{MSADS_CUSTOMER_ID}</CustomerId>
    <DeveloperToken>{MSADS_DEVELOPER_TOKEN}</DeveloperToken>
  </s:Header>
  <s:Body>
    <SubmitGenerateReportRequest xmlns="https://bingads.microsoft.com/Reporting/v13">
      <ReportRequest i:type="CampaignPerformanceReportRequest">
        <ExcludeColumnHeaders>false</ExcludeColumnHeaders>
        <ExcludeReportFooter>true</ExcludeReportFooter>
        <ExcludeReportHeader>true</ExcludeReportHeader>
        <Format>Csv</Format>
        <FormatVersion>2.0</FormatVersion>
        <ReportName>Microsoft Ads Weekly Campaign Report</ReportName>
        <ReturnOnlyCompleteData>false</ReturnOnlyCompleteData>
        <Aggregation>WeeklyStartingMonday</Aggregation>
        <Columns xmlns:a="https://bingads.microsoft.com/Reporting/v13">
          <a:CampaignPerformanceReportColumn>TimePeriod</a:CampaignPerformanceReportColumn>
          <a:CampaignPerformanceReportColumn>CampaignId</a:CampaignPerformanceReportColumn>
          <a:CampaignPerformanceReportColumn>CampaignName</a:CampaignPerformanceReportColumn>
          <a:CampaignPerformanceReportColumn>Impressions</a:CampaignPerformanceReportColumn>
          <a:CampaignPerformanceReportColumn>Clicks</a:CampaignPerformanceReportColumn>
          <a:CampaignPerformanceReportColumn>Spend</a:CampaignPerformanceReportColumn>
        </Columns>
        <Filter i:nil="true" />
        <Scope xmlns:a="https://bingads.microsoft.com/Reporting/v13">
          <a:AccountIds xmlns:b="http://schemas.microsoft.com/2003/10/Serialization/Arrays">
            <b:long>{MSADS_ACCOUNT_ID}</b:long>
          </a:AccountIds>
          <a:Campaigns i:nil="true" />
        </Scope>
        <Time>
          <CustomDateRangeStart i:nil="true" />
          <CustomDateRangeEnd i:nil="true" />
          <PredefinedTime>LastWeekStartingMonday</PredefinedTime>
          <ReportTimeZone>AmsterdamBerlinBernRomeStockholmVienna</ReportTimeZone>
        </Time>
      </ReportRequest>
    </SubmitGenerateReportRequest>
  </s:Body>
</s:Envelope>"""

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "SubmitGenerateReport",
    }

    response = requests.post(url, headers=headers, data=body.encode("utf-8"), timeout=60)
    response.raise_for_status()
    return response.text


def poll_report(access_token: str, report_request_id: str):
    url = "https://reporting.api.bingads.microsoft.com/Api/Advertiser/Reporting/v13/ReportingService.svc"

    body = f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:i="http://www.w3.org/2001/XMLSchema-instance" xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Header xmlns="https://bingads.microsoft.com/Reporting/v13">
    <Action mustUnderstand="1">PollGenerateReport</Action>
    <AuthenticationToken>{access_token}</AuthenticationToken>
    <CustomerAccountId>{MSADS_ACCOUNT_ID}</CustomerAccountId>
    <CustomerId>{MSADS_CUSTOMER_ID}</CustomerId>
    <DeveloperToken>{MSADS_DEVELOPER_TOKEN}</DeveloperToken>
  </s:Header>
  <s:Body>
    <PollGenerateReportRequest xmlns="https://bingads.microsoft.com/Reporting/v13">
      <ReportRequestId>{report_request_id}</ReportRequestId>
    </PollGenerateReportRequest>
  </s:Body>
</s:Envelope>"""

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "PollGenerateReport",
    }

    response = requests.post(url, headers=headers, data=body.encode("utf-8"), timeout=60)
    response.raise_for_status()
    return response.text


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
    campaigns_by_clean_name = {}
    duplicates = {}
    duplicate_names = {}

    for campaign in results:
        hubspot_campaign_id = campaign.get("id")
        properties = campaign.get("properties", {})
        hs_name = properties.get("hs_name", "")
        msads_campaign_id = properties.get("msads_campaign_id", "")
        clean_name = sanitize_campaign_name(hs_name)

        if msads_campaign_id:
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

        if clean_name:
            if clean_name in campaigns_by_clean_name:
                duplicate_names.setdefault(clean_name, []).append({
                    "id": hubspot_campaign_id,
                    "hs_name": hs_name,
                })
            else:
                campaigns_by_clean_name[clean_name] = {
                    "id": hubspot_campaign_id,
                    "hs_name": hs_name,
                }

    if duplicates:
        raise ValueError(f"Duplicate msads_campaign_id values found: {', '.join(duplicates.keys())}")

    return campaigns_by_msads_id, campaigns_by_clean_name, duplicate_names


def sync_rows(report_rows, campaigns_by_msads_id, campaigns_by_clean_name, duplicate_names, hubspot_headers):
    processed_ids = set()

    for report_row in report_rows:
        msads_id = report_row["CampaignId"]

        if not msads_id:
            print("SKIP missing CampaignId")
            continue

        if msads_id in processed_ids:
            print(f"SKIP already processed CampaignId: {msads_id}")
            continue

        processed_ids.add(msads_id)

        clean_name = sanitize_campaign_name(report_row["CampaignName"])
        match = campaigns_by_msads_id.get(msads_id)

        payload = {
            "properties": {
                "msads_campaign_id": msads_id,
                "msads_impressions": report_row["Impressions"],
                "msads_clicks": report_row["Clicks"],
                "msads_spend_eur": report_row["Spend"],
                "msads_status": report_row["Status"],
            }
        }

        if match:
            patch_url = f"https://api.hubapi.com/marketing/v3/campaigns/{match['id']}"
            patch_response = requests.patch(patch_url, headers=hubspot_headers, json=payload, timeout=30)
            patch_response.raise_for_status()
            updated = patch_response.json()
            print("PATCH OK")
            print(updated["id"])
            continue

        if clean_name in duplicate_names:
            print(f"SKIP duplicate sanitized name in HubSpot: {clean_name}")
            continue

        name_match = campaigns_by_clean_name.get(clean_name)
        if name_match:
            patch_url = f"https://api.hubapi.com/marketing/v3/campaigns/{name_match['id']}"
            patch_response = requests.patch(patch_url, headers=hubspot_headers, json=payload, timeout=30)
            patch_response.raise_for_status()
            updated = patch_response.json()
            print("PATCH BY NAME OK")
            print(updated["id"])
            continue

        create_payload = {
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
        create_response = requests.post(create_url, headers=hubspot_headers, json=create_payload, timeout=30)
        create_response.raise_for_status()
        created = create_response.json()
        print("POST OK")
        print(created["id"])


access_token = refresh_msads_access_token()
print("Access token OK")

submit_xml = submit_report(access_token)
report_request_id = extract_first_tag(submit_xml, "ReportRequestId")
if not report_request_id:
    raise ValueError(f"No ReportRequestId found in submit response:\n{submit_xml}")

print(f"ReportRequestId: {report_request_id}")

download_url = None
last_poll_xml = None

for _ in range(12):
    time.sleep(5)
    poll_xml = poll_report(access_token, report_request_id)
    last_poll_xml = poll_xml
    status = extract_first_tag(poll_xml, "Status")
    print(f"Report status: {status}")

    if status == "Success":
        download_url = extract_first_tag(poll_xml, "ReportDownloadUrl")
        if download_url:
            break
    elif status == "Error":
        raise ValueError(f"Report failed:\n{poll_xml}")

if not download_url:
    raise ValueError(f"No ReportDownloadUrl found in poll response:\n{last_poll_xml}")

report_rows = download_and_parse_report(download_url)
print(f"Downloaded report rows: {len(report_rows)}")

hubspot_data, hubspot_headers = get_hubspot_campaigns()
campaigns_by_msads_id, campaigns_by_clean_name, duplicate_names = build_hubspot_lookup(
    hubspot_data.get("results", [])
)

sync_rows(
    report_rows,
    campaigns_by_msads_id,
    campaigns_by_clean_name,
    duplicate_names,
    hubspot_headers,
)
