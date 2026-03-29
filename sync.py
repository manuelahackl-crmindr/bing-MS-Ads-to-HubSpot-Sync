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
