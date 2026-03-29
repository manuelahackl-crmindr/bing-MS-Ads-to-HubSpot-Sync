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
    token_data = response.json()
    return token_data["access_token"]


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


def extract_first_tag(xml_text: str, tag_name: str):
    root = ET.fromstring(xml_text)
    for elem in root.iter():
        if elem.tag.endswith(tag_name):
            return elem.text
    return None


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


access_token = refresh_msads_access_token()
print("Access token OK")

submit_xml = submit_report(access_token)
report_request_id = extract_first_tag(submit_xml, "ReportRequestId")

if not report_request_id:
    raise ValueError("No ReportRequestId found")

print(f"ReportRequestId: {report_request_id}")

download_url = None
for _ in range(10):
    time.sleep(5)
    poll_xml = poll_report(access_token, report_request_id)
    status = extract_first_tag(poll_xml, "Status")
    print(f"Report status: {status}")
    if status == "Success":
        download_url = extract_first_tag(poll_xml, "ReportDownloadUrl")
        break

if not download_url:
    raise ValueError("No ReportDownloadUrl found")

report_rows = download_and_parse_report(download_url)
print(f"Downloaded report rows: {len(report_rows)}")

for row in report_rows[:5]:
    print(row)
