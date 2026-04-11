import os
import re
import csv
import io
import time
import zipfile
from datetime import datetime, date
import requests
import xml.etree.ElementTree as ET

HUBSPOT_TOKEN = os.getenv("HUBSPOT_TOKEN")
MSADS_CLIENT_ID = os.getenv("MSADS_CLIENT_ID")
MSADS_CLIENT_SECRET = os.getenv("MSADS_CLIENT_SECRET")
MSADS_REFRESH_TOKEN = os.getenv("MSADS_REFRESH_TOKEN")
MSADS_DEVELOPER_TOKEN = os.getenv("MSADS_DEVELOPER_TOKEN")
MSADS_CUSTOMER_ID = os.getenv("MSADS_CUSTOMER_ID")
MSADS_ACCOUNT_ID = os.getenv("MSADS_ACCOUNT_ID")

BACKFILL_START_WEEK = os.getenv("BACKFILL_START_WEEK", "")
BACKFILL_END_WEEK = os.getenv("BACKFILL_END_WEEK", "")
BACKFILL_YEAR = os.getenv("BACKFILL_YEAR", "")

required = [
    "HUBSPOT_TOKEN",
    "MSADS_CLIENT_ID",
    "MSADS_CLIENT_SECRET",
    "MSADS_REFRESH_TOKEN",
    "MSADS_DEVELOPER_TOKEN",
    "MSADS_CUSTOMER_ID",
    "MSADS_ACCOUNT_ID",
    "BACKFILL_START_WEEK",
    "BACKFILL_END_WEEK",
    "BACKFILL_YEAR",
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


def build_columns_xml():
    columns = [
        "<a:CampaignPerformanceReportColumn>CampaignId</a:CampaignPerformanceReportColumn>",
        "<a:CampaignPerformanceReportColumn>CampaignName</a:CampaignPerformanceReportColumn>",
        "<a:CampaignPerformanceReportColumn>CampaignStatus</a:CampaignPerformanceReportColumn>",
        "<a:CampaignPerformanceReportColumn>Impressions</a:CampaignPerformanceReportColumn>",
        "<a:CampaignPerformanceReportColumn>Clicks</a:CampaignPerformanceReportColumn>",
        "<a:CampaignPerformanceReportColumn>Spend</a:CampaignPerformanceReportColumn>",
    ]
    return "\n".join(columns)


def build_time_xml_custom(start_date: date, end_date: date):
    return f"""
        <Time>
          <CustomDateRangeEnd>
            <Day>{end_date.day}</Day>
            <Month>{end_date.month}</Month>
            <Year>{end_date.year}</Year>
          </CustomDateRangeEnd>
          <CustomDateRangeStart>
            <Day>{start_date.day}</Day>
            <Month>{start_date.month}</Month>
            <Year>{start_date.year}</Year>
          </CustomDateRangeStart>
          <PredefinedTime i:nil="true" />
          <ReportTimeZone>AmsterdamBerlinBernRomeStockholmVienna</ReportTimeZone>
        </Time>
    """


def submit_report(access_token: str, start_date: date, end_date: date):
    url = "https://reporting.api.bingads.microsoft.com/Api/Advertiser/Reporting/v13/ReportingService.svc"
    columns_xml = build_columns_xml()
    time_xml = build_time_xml_custom(start_date, end_date)

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
        <ReportName>Microsoft Ads Missing Campaign Discovery</ReportName>
        <ReturnOnlyCompleteData>false</ReturnOnlyCompleteData>
        <Aggregation>Summary</Aggregation>
        <Columns xmlns:a="https://bingads.microsoft.com/Reporting/v13">
          {columns_xml}
        </Columns>
        <Filter i:nil="true" />
        <Scope xmlns:a="https://bingads.microsoft.com/Reporting/v13">
          <a:AccountIds xmlns:b="http://schemas.microsoft.com/2003/10/Serialization/Arrays">
            <b:long>{MSADS_ACCOUNT_ID}</b:long>
          </a:AccountIds>
          <a:Campaigns i:nil="true" />
        </Scope>
        {time_xml}
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
            "Status": str(row.get("CampaignStatus", "")).strip() or "Active",
            "Impressions": str(row.get("Impressions", "")).strip(),
            "Clicks": str(row.get("Clicks", "")).strip(),
            "Spend": str(row.get("Spend", "")).strip(),
        })
    return rows


def fetch_report_rows_for_range(access_token: str, start_date: date, end_date: date):
    submit_xml = submit_report(access_token=access_token, start_date=start_date, end_date=end_date)

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

    rows = download_and_parse_report(download_url)
    print(f"Downloaded report rows: {len(rows)}")
    return rows


def get_backfill_weeks():
    start_week = int(BACKFILL_START_WEEK)
    end_week = int(BACKFILL_END_WEEK)
    year = int(BACKFILL_YEAR)

    if end_week < start_week:
        raise ValueError("BACKFILL_END_WEEK must be >= BACKFILL_START_WEEK")

    jan1 = date(year, 1, 1)
    today = date.today()

    weeks = []
    for week in range(start_week, end_week + 1):
        monday = date.fromisocalendar(year, week, 1)
        sunday = date.fromisocalendar(year, week, 7)

        effective_start = monday if monday >= jan1 else jan1
        effective_end = sunday if sunday <= today else today

        if effective_end < effective_start:
            print(f"SKIP week {year}-KW{str(week).zfill(2)} because effective_end < effective_start")
            continue

        weeks.append({
            "year": year,
            "week": week,
            "start_date": effective_start,
            "end_date": effective_end,
        })
    return weeks


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
    duplicate_names = {}

    for campaign in results:
        hubspot_campaign_id = campaign.get("id")
        properties = campaign.get("properties", {})
        hs_name = properties.get("hs_name", "")
        msads_campaign_id = properties.get("msads_campaign_id", "")
        clean_name = sanitize_campaign_name(hs_name)

        if msads_campaign_id and msads_campaign_id not in campaigns_by_msads_id:
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

    return campaigns_by_msads_id, campaigns_by_clean_name, duplicate_names


def collect_unique_campaign_rows(all_rows):
    unique = {}
    for row in all_rows:
        campaign_id = row["CampaignId"]
        if not campaign_id:
            continue
        if campaign_id not in unique:
            unique[campaign_id] = row
    return list(unique.values())


def create_missing_campaigns(rows, campaigns_by_msads_id, campaigns_by_clean_name, duplicate_names, hubspot_headers):
    created_count = 0
    skipped_existing_id = 0
    skipped_existing_name = 0
    skipped_duplicate_name = 0

    for row in rows:
        msads_id = row["CampaignId"]
        clean_name = sanitize_campaign_name(row["CampaignName"])

        if msads_id in campaigns_by_msads_id:
            print(f"EXISTS BY ID - SKIP: {msads_id} | {clean_name}")
            skipped_existing_id += 1
            continue

        if clean_name in duplicate_names:
            print(f"DUPLICATE NAME IN HUBSPOT - SKIP: {msads_id} | {clean_name}")
            skipped_duplicate_name += 1
            continue

        if clean_name in campaigns_by_clean_name:
            print(f"EXISTS BY NAME - SKIP (NO PATCH): {msads_id} | {clean_name}")
            skipped_existing_name += 1
            continue

        create_payload = {
            "properties": {
                "hs_name": clean_name,
                "hs_notes": "bing",
                "msads_campaign_id": msads_id,
                "msads_impressions": row["Impressions"],
                "msads_clicks": row["Clicks"],
                "msads_spend_eur": row["Spend"],
                "msads_status": row["Status"],
            }
        }

        create_url = "https://api.hubapi.com/marketing/v3/campaigns"
        response = requests.post(create_url, headers=hubspot_headers, json=create_payload, timeout=30)

        if response.status_code >= 400:
            print("CREATE CAMPAIGN ERROR")
            print(response.status_code)
            print(response.text)
            response.raise_for_status()

        created = response.json()
        print(f"CREATED: {msads_id} | {clean_name} | {created['id']}")
        created_count += 1

        campaigns_by_msads_id[msads_id] = {
            "id": created["id"],
            "hs_name": clean_name,
        }
        campaigns_by_clean_name[clean_name] = {
            "id": created["id"],
            "hs_name": clean_name,
        }

    print("SUMMARY")
    print(f"Created campaigns: {created_count}")
    print(f"Skipped existing by ID: {skipped_existing_id}")
    print(f"Skipped existing by name: {skipped_existing_name}")
    print(f"Skipped duplicate names: {skipped_duplicate_name}")


def main():
    access_token = refresh_msads_access_token()
    print("Access token OK")

    weeks = get_backfill_weeks()
    print(f"Weeks to scan: {len(weeks)}")

    all_rows = []
    for week in weeks:
        print(
            f"Processing week {week['year']}-KW{str(week['week']).zfill(2)} "
            f"({week['start_date']} to {week['end_date']})"
        )
        rows = fetch_report_rows_for_range(
            access_token=access_token,
            start_date=week["start_date"],
            end_date=week["end_date"],
        )
        all_rows.extend(rows)

    unique_rows = collect_unique_campaign_rows(all_rows)
    print(f"Unique campaign IDs found in scanned range: {len(unique_rows)}")

    hubspot_data, hubspot_headers = get_hubspot_campaigns()
    campaigns_by_msads_id, campaigns_by_clean_name, duplicate_names = build_hubspot_lookup(
        hubspot_data.get("results", [])
    )

    create_missing_campaigns(
        rows=unique_rows,
        campaigns_by_msads_id=campaigns_by_msads_id,
        campaigns_by_clean_name=campaigns_by_clean_name,
        duplicate_names=duplicate_names,
        hubspot_headers=hubspot_headers,
    )


if __name__ == "__main__":
    main()
