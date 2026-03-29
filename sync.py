import os

required = [
    "MSADS_CLIENT_ID",
    "MSADS_CLIENT_SECRET",
    "MSADS_REFRESH_TOKEN",
    "MSADS_DEVELOPER_TOKEN",
    "MSADS_CUSTOMER_ID",
    "MSADS_ACCOUNT_ID",
    "HUBSPOT_TOKEN",
]

missing = [key for key in required if not os.getenv(key)]

if missing:
    raise ValueError(f"Missing secrets: {', '.join(missing)}")

print("All secrets are available")
