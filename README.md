## Bing to HubSpot Sync
MSAds to HubSpot Sync is a one-way data integration between Microsoft Advertising (Bing Ads) and HubSpot.
Repository name: bing-MS-Ads-to-HubSpot-Sync
 (client project)

 ## Project Description

MSAds to HubSpot Sync is a one-way data integration between Microsoft Advertising (Bing Ads) and HubSpot.

The integration retrieves advertising performance data from Microsoft Advertising on a weekly basis and transfers the relevant information to HubSpot. The data is used to update dedicated HubSpot Project objects, creating a historical record of weekly Bing Ads performance.

In addition, the synchronized data supports internal reporting and data management within HubSpot, including dashboards, reports, and other CRM objects.

## Technologies & Platforms

- **Microsoft Advertising (Bing Ads):** Source platform for advertising performance data.
- **HubSpot:** Destination CRM and reporting platform.
- **HubSpot API:** API integration used to retrieve and update HubSpot data.
- **Microsoft Azure:** Infrastructure used to establish and manage the connection between HubSpot and Microsoft Advertising.

## Key Features

- One-way data synchronization from Microsoft Advertising to HubSpot.
- Weekly retrieval and transfer of Bing Ads performance data.
- Automatic updates of dedicated HubSpot Project objects to document weekly advertising performance.
- Creation and maintenance of internal reporting resources in HubSpot.
- Data provision for HubSpot dashboards, reports, and other CRM objects.
- Updates to advertising source information and UTM parameters in:
  - Contact objects
  - Deal objects
  - Company objects
- Data mapping and field matching to ensure information is written to the corresponding HubSpot properties.

## Data Flow

The integration follows a one-way synchronization process:

1. Microsoft Advertising provides the advertising performance data.
2. The connection is established through the configured Azure infrastructure and the required Microsoft Advertising permissions.
3. The integration retrieves the relevant data on a weekly basis.
4. Data is mapped to the corresponding HubSpot properties according to the configured field mapping.
5. HubSpot Project objects are updated to maintain weekly advertising performance records.
6. Relevant source information and UTM parameters are written to Contact, Deal, and Company objects.
7. The synchronized information is made available for internal HubSpot reporting, dashboards, and other CRM resources.

**Data direction:** Microsoft Advertising → HubSpot

## How to Run

The integration is configured for weekly data synchronization.

To use or maintain the integration:

1. Ensure that the required Microsoft Advertising permissions and access credentials are available.
2. Ensure that the Azure connection between Microsoft Advertising and HubSpot is configured and operational.
3. Verify that the HubSpot API connection and required permissions are active.
4. Check that the HubSpot Project objects and corresponding properties are available.
5. Verify the configured field mapping between the source data and HubSpot properties.
6. Execute or allow the configured weekly synchronization process to run.
7. Review the updated Project objects and verify that the relevant CRM properties and reporting resources have been populated correctly.

*Note: Execution and deployment details depend on the existing Azure configuration.*

## Access & Usage Restrictions

**Exclusive customer use: Memox**
This integration has been developed specifically for Memox and is intended exclusively for use within the Memox environment.

The implementation, configuration, and associated workflows are customer-specific. If the solution is reused, it must be copied and adapted to the respective environment, including the relevant API credentials, permissions, Azure configuration, HubSpot properties, and data mappings.

Use outside the Memox environment requires appropriate authorization.

## Author

**Manuela Hackl**
CRM & Automation | HubSpot Integration
