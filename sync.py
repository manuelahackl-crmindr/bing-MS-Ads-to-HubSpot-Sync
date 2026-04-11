import os
import re
import csv
import io
import time
import zipfile
from datetime import datetime, date, timedelta
import requests
import xml.etree.ElementTree as ET

HUBSPOT_TOKEN = os.getenv("HUBSPOT_TOKEN")
MSADS_CLIENT_ID = os.getenv("MSADS_CLIENT_ID")
MSADS_CLIENT_SECRET = os.getenv("MSADS_CLIENT_SECRET")
MSADS_REFRESH_TOKEN = os.getenv("MSADS_REFRESH_TOKEN")
MSADS_DEVELOPER_TOKEN = os.getenv("MSADS_DEVELOPER_TOKEN")
MSADS_CUSTOMER_ID = os.getenv("MSADS_CUSTOMER_ID")
MSADS_ACCOUNT_ID = os.getenv("MSADS_ACCOUNT_ID")

BACKFILL_MODE = os.getenv("BACKFILL_MODE", "false").lower() == "true"
BACKFILL_START_WEEK = os.getenv("BACKFILL_START_WEEK", "")
BACKFILL_END_WEEK = os.getenv("BACKFILL_END_WEEK", "")
BACKFILL_YEAR = os.getenv("BACKFILL_YEAR", "")

PROJECT_PIPELINE_ID = "885593491"
PROJECT_STAGE_ACTIVE = "1332176280"      # Execution
PROJECT_STAGE_PAUSED = "1332176283"      # On Hold
PROJECT_STAGE_ENDED = "1332176282"       # Completed
PROJECT_STAGE_CANCELLED = "1332176284"   # Cancelled

PROJECT_STATUS_PROPERTY = "hs_status"
PROJECT_STATUS_ACTIVE = "on_track"
PROJECT_STATUS_PAUSED = "on_hold"
PROJECT_STATUS_ENDED = "completed"
PROJECT_STATUS_CANCELLED = "blocked"

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


def normalize_msads_status(status_value: str) -> str:
    value = (status_value or "").strip().lower()
    value = value.replace(" ", "_").replace("-", "_")

    alias_map = {
        "active": "active",
        "paused": "paused",
        "budgetpaused": "budget_paused",
        "budget_paused": "budget_paused",
        "budgetandmanualpaused": "budget_and_manual_paused",
        "budget_and_manual_paused": "budget_and_manual_paused",
        "ended": "ended",
        "suspended": "suspended",
        "deleted": "deleted",
    }
    return alias_map.get(value, value)


def build_columns_xml(include_timeperiod: bool):
    columns = []
    if include_timeperiod:
        columns.append("<a:CampaignPerformanceReportColumn>TimePeriod</a:CampaignPerformanceReportColumn>")

    columns.extend([
        "<a:CampaignPerformanceReportColumn>CampaignId</a:CampaignPerformanceReportColumn>",
        "<a:CampaignPerformanceReportColumn>CampaignName</a:CampaignPerformanceReportColumn>",
        "<a:CampaignPerformanceReportColumn>CampaignStatus</a:CampaignPerformanceReportColumn>",
        "<a:CampaignPerformanceReportColumn>Impressions</a:CampaignPerformanceReportColumn>",
        "<a:CampaignPerformanceReportColumn>Clicks</a:CampaignPerformanceReportColumn>",
        "<a:CampaignPerformanceReportColumn>Spend</a:CampaignPerformanceReportColumn>",
    ])
    return "\n".join(columns)


def build_time_xml_predefined():
    return """
        <Time>
          <CustomDateRangeStart i:nil="true" />
          <CustomDateRangeEnd i:nil="true" />
          <PredefinedTime>LastWeekStartingMonday</PredefinedTime>
          <ReportTimeZone>AmsterdamBerlinBernRomeStockholmVienna</ReportTimeZone>
        </Time>
    """


def build_time_xml_custom(start_date: date, end_date: date):
    return f"""
        <Time>
          <CustomDateRangeStart>
            <Day>{start_date.day}</Day>
            <Month>{start_date.month}</Month>
            <Year>{start_date.year}</Year>
          </CustomDateRangeStart>
          <CustomDateRangeEnd>
            <Day>{end_date.day}</Day>
            <Month>{end_date.month}</Month>
            <Year>{end_date.year}</Year>
          </CustomDateRangeEnd>
          <PredefinedTime i:nil="true" />
          <ReportTimeZone>AmsterdamBerlinBernRomeStockholmVienna</ReportTimeZone>
        </Time>
    """


def submit_report(
    access_token: str,
    start_date: date = None,
    end_date: date = None,
    aggregation: str = "WeeklyStartingMonday",
    include_timeperiod: bool = True,
):
    url = "https://reporting.api.bingads.microsoft.com/Api/Advertiser/Reporting/v13/ReportingService.svc"

    time_xml = build_time_xml_custom(start_date, end_date) if start_date and end_date else build_time_xml_predefined()
    columns_xml = build_columns_xml(include_timeperiod)

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
        <ReportName>Microsoft Ads Campaign Report</ReportName>
        <ReturnOnlyCompleteData>false</ReturnOnlyCompleteData>
        <Aggregation>{aggregation}</Aggregation>
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


def parse_timeperiod_to_week_fields(time_period: str):
    if not time_period:
        raise ValueError("Missing TimePeriod")

    base = time_period[:10]
    week_start_dt = datetime.strptime(base, "%Y-%m-%d").date()
    iso = week_start_dt.isocalendar()

    return {
        "week_start": week_start_dt.isoformat(),
        "year": str(iso.year),
        "calendar_week": str(iso.week),
        "week_key": f"{iso.year}-KW{iso.week:02d}",
    }


def download_and_parse_report(download_url: str, forced_time_period: str = None):
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
            "TimePeriod": forced_time_period if forced_time_period else str(row.get("TimePeriod", "")).strip(),
            "CampaignId": str(row.get("CampaignId", "")).strip(),
            "CampaignName": str(row.get("CampaignName", "")).strip(),
            "Status": str(row.get("CampaignStatus", "")).strip() or "Active",
            "Impressions": str(row.get("Impressions", "")).strip(),
            "Clicks": str(row.get("Clicks", "")).strip(),
            "Spend": str(row.get("Spend", "")).strip(),
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


def get_project_stage_id(status_value: str) -> str:
    status = normalize_msads_status(status_value)

    if status in {"paused", "budget_paused", "budget_and_manual_paused"}:
        return PROJECT_STAGE_PAUSED
    if status == "ended":
        return PROJECT_STAGE_ENDED
    if status in {"suspended", "deleted"}:
        return PROJECT_STAGE_CANCELLED
    return PROJECT_STAGE_ACTIVE


def get_project_status_value(status_value: str) -> str:
    status = normalize_msads_status(status_value)

    if status in {"paused", "budget_paused", "budget_and_manual_paused"}:
        return PROJECT_STATUS_PAUSED
    if status == "ended":
        return PROJECT_STATUS_ENDED
    if status in {"suspended", "deleted"}:
        return PROJECT_STATUS_CANCELLED
    return PROJECT_STATUS_ACTIVE


def build_project_name(year: str, kw: str, campaign_name: str, campaign_id: str) -> str:
    return f"MS Ads | {year} | KW{kw} - {campaign_name} | {campaign_id}"[:256]


def find_project_by_name(project_name: str, hubspot_headers: dict):
    search_url = "https://api.hubapi.com/crm/v3/objects/projects/search"
    payload = {
        "filterGroups": [
            {
                "filters": [
                    {
                        "propertyName": "hs_name",
                        "operator": "EQ",
                        "value": project_name,
                    }
                ]
            }
        ],
        "limit": 1,
        "properties": ["hs_name"],
    }

    response = requests.post(search_url, headers=hubspot_headers, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    results = data.get("results", [])

    if results:
        return results[0]
    return None


def upsert_project_for_row(report_row: dict, hubspot_headers: dict):
    week_fields = parse_timeperiod_to_week_fields(report_row["TimePeriod"])
    clean_name = sanitize_campaign_name(report_row["CampaignName"])
    campaign_id = report_row["CampaignId"]
    status_value = report_row["Status"]

    project_name = build_project_name(
        year=week_fields["year"],
        kw=week_fields["calendar_week"],
        campaign_name=clean_name,
        campaign_id=campaign_id,
    )

    project_payload = {
        "properties": {
            "hs_name": project_name,
            "hs_pipeline": PROJECT_PIPELINE_ID,
            "hs_pipeline_stage": get_project_stage_id(status_value),
            PROJECT_STATUS_PROPERTY: get_project_status_value(status_value),
            "msads_campaign_id": campaign_id,
            "msads_campaign_name": clean_name,
            "msads_week_key": week_fields["week_key"],
            "msads_week_start": week_fields["week_start"],
            "msads_year": week_fields["year"],
            "msads_calendar_week": week_fields["calendar_week"],
            "msads_impressions": report_row["Impressions"],
            "msads_clicks": report_row["Clicks"],
            "msads_spend_eur": report_row["Spend"],
        }
    }

    existing_project = find_project_by_name(project_name, hubspot_headers)

    if existing_project:
        project_id = existing_project["id"]
        patch_url = f"https://api.hubapi.com/crm/v3/objects/projects/{project_id}"
        response = requests.patch(patch_url, headers=hubspot_headers, json=project_payload, timeout=30)

        if response.status_code >= 400:
            print("PROJECT PATCH ERROR")
            print(response.status_code)
            print(response.text)
            response.raise_for_status()

        updated = response.json()
        print("PROJECT PATCH OK")
        print(updated["id"])
        return

    create_url = "https://api.hubapi.com/crm/v3/objects/projects"
    response = requests.post(create_url, headers=hubspot_headers, json=project_payload, timeout=30)

    if response.status_code >= 400:
        print("PROJECT CREATE ERROR")
        print(response.status_code)
        print(response.text)
        response.raise_for_status()

    created = response.json()
    print("PROJECT POST OK")
    print(created["id"])


def sync_rows(report_rows, campaigns_by_msads_id, campaigns_by_clean_name, duplicate_names, hubspot_headers, backfill_mode: bool = False):
    processed_hubspot_campaign_week_keys = set()
    processed_project_keys = set()

    for report_row in report_rows:
        msads_id = report_row["CampaignId"]

        if not msads_id:
            print("SKIP missing CampaignId")
            continue

        week_fields = parse_timeperiod_to_week_fields(report_row["TimePeriod"])
        project_key = f"{week_fields['week_key']}|{msads_id}"

        if project_key in processed_project_keys:
            print(f"SKIP already processed project key: {project_key}")
            continue

        clean_name = sanitize_campaign_name(report_row["CampaignName"])
        match = campaigns_by_msads_id.get(msads_id)

        target_hubspot_campaign_id = None
        action_type = None

        if match:
            target_hubspot_campaign_id = match["id"]
            action_type = "PATCH"
        else:
            if clean_name in duplicate_names:
                raise ValueError(f"Duplicate sanitized campaign name in HubSpot: {clean_name}")

            name_match = campaigns_by_clean_name.get(clean_name)
            if name_match:
                target_hubspot_campaign_id = name_match["id"]
                action_type = "PATCH_BY_NAME"
            else:
                action_type = "POST"

        campaign_week_key = None
        if target_hubspot_campaign_id:
            campaign_week_key = f"{week_fields['week_key']}|{target_hubspot_campaign_id}"

        if campaign_week_key and campaign_week_key in processed_hubspot_campaign_week_keys:
            print(f"SKIP already processed HubSpot campaign in this week: {campaign_week_key}")
            processed_project_keys.add(project_key)
            continue

        if backfill_mode:
            if action_type == "POST":
                print(f"BACKFILL SKIP no existing HubSpot campaign for CampaignId={msads_id} CampaignName={report_row['CampaignName']}")
                processed_project_keys.add(project_key)
                continue

            print(f"BACKFILL PROJECT for {project_key}")
            upsert_project_for_row(report_row, hubspot_headers)

            if campaign_week_key:
                processed_hubspot_campaign_week_keys.add(campaign_week_key)
            processed_project_keys.add(project_key)
            continue

        payload = {
            "properties": {
                "msads_campaign_id": msads_id,
                "msads_impressions": report_row["Impressions"],
                "msads_clicks": report_row["Clicks"],
                "msads_spend_eur": report_row["Spend"],
                "msads_status": report_row["Status"],
            }
        }

        if action_type == "PATCH":
            patch_url = f"https://api.hubapi.com/marketing/v3/campaigns/{target_hubspot_campaign_id}"
            patch_response = requests.patch(patch_url, headers=hubspot_headers, json=payload, timeout=30)
            patch_response.raise_for_status()
            updated = patch_response.json()
            print("PATCH OK")
            print(updated["id"])
            upsert_project_for_row(report_row, hubspot_headers)
            if campaign_week_key:
                processed_hubspot_campaign_week_keys.add(campaign_week_key)
            processed_project_keys.add(project_key)
            continue

        if action_type == "PATCH_BY_NAME":
            patch_url = f"https://api.hubapi.com/marketing/v3/campaigns/{target_hubspot_campaign_id}"
            patch_response = requests.patch(patch_url, headers=hubspot_headers, json=payload, timeout=30)
            patch_response.raise_for_status()
            updated = patch_response.json()
            print("PATCH BY NAME OK")
            print(updated["id"])
            upsert_project_for_row(report_row, hubspot_headers)
            if campaign_week_key:
                processed_hubspot_campaign_week_keys.add(campaign_week_key)
            processed_project_keys.add(project_key)
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

        upsert_project_for_row(report_row, hubspot_headers)
        new_campaign_week_key = f"{week_fields['week_key']}|{created['id']}"
        processed_hubspot_campaign_week_keys.add(new_campaign_week_key)
        processed_project_keys.add(project_key)


def get_backfill_weeks():
    if not BACKFILL_MODE:
        return []

    if not BACKFILL_START_WEEK or not BACKFILL_END_WEEK or not BACKFILL_YEAR:
        raise ValueError("BACKFILL_MODE is true but BACKFILL_START_WEEK / BACKFILL_END_WEEK / BACKFILL_YEAR are missing")

    start_week = int(BACKFILL_START_WEEK)
    end_week = int(BACKFILL_END_WEEK)
    year = int(BACKFILL_YEAR)

    if end_week < start_week:
        raise ValueError("BACKFILL_END_WEEK must be >= BACKFILL_START_WEEK")

    weeks = []
    for week in range(start_week, end_week + 1):
        monday = date.fromisocalendar(year, week, 1)
        sunday = date.fromisocalendar(year, week, 7)
        weeks.append({
            "year": year,
            "week": week,
            "start_date": monday,
            "end_date": sunday,
            "time_period": monday.isoformat(),
        })
    return weeks


def fetch_report_rows(access_token: str, start_date: date = None, end_date: date = None, forced_time_period: str = None):
    submit_xml = submit_report(
        access_token=access_token,
        start_date=start_date,
        end_date=end_date,
        aggregation="Summary" if start_date and end_date else "WeeklyStartingMonday",
        include_timeperiod=False if start_date and end_date else True,
    )

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

    rows = download_and_parse_report(download_url, forced_time_period=forced_time_period)
    print(f"Downloaded report rows: {len(rows)}")
    return rows


def main():
    access_token = refresh_msads_access_token()
    print("Access token OK")

    hubspot_data, hubspot_headers = get_hubspot_campaigns()
    campaigns_by_msads_id, campaigns_by_clean_name, duplicate_names = build_hubspot_lookup(
        hubspot_data.get("results", [])
    )

    if BACKFILL_MODE:
        print("BACKFILL MODE ON")
        weeks = get_backfill_weeks()
        print(f"Backfill weeks: {len(weeks)}")

        for week in weeks:
            print(
                f"Processing week {week['year']}-KW{str(week['week']).zfill(2)} "
                f"({week['start_date']} to {week['end_date']})"
            )

            report_rows = fetch_report_rows(
                access_token=access_token,
                start_date=week["start_date"],
                end_date=week["end_date"],
                forced_time_period=week["time_period"],
            )

            sync_rows(
                report_rows,
                campaigns_by_msads_id,
                campaigns_by_clean_name,
                duplicate_names,
                hubspot_headers,
                backfill_mode=True,
            )
        return

    report_rows = fetch_report_rows(access_token=access_token)

    sync_rows(
        report_rows,
        campaigns_by_msads_id,
        campaigns_by_clean_name,
        duplicate_names,
        hubspot_headers,
        backfill_mode=False,
    )


if __name__ == "__main__":
    main()
