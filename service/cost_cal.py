from functools import lru_cache
import requests
import difflib

API_VERSION = "2023-01-01-preview"

BASE_URL = (
    f"https://prices.azure.com/api/retail/prices"
    f"?api-version={API_VERSION}"
)

HEADERS = {
    "User-Agent": "AzureVMRightsizer/1.0",
    "Accept": "application/json",
}


REGION_MAP = {
    "East US": "eastus",
    "East US 2": "eastus2",
    "West US": "westus",
    "West US 2": "westus2",
    "West US 3": "westus3",
    "Central US": "centralus",
    "North Europe": "northeurope",
    "West Europe": "westeurope",
    "Southeast Asia": "southeastasia",
    "South India": "southindia",
    "Central India": "centralindia",
    "West India": "westindia",
}

def normalize_region(region):
    if not region:
        return ""

    return REGION_MAP.get(
        region.strip(),
        region.strip().lower().replace(" ", "")
    )
def normalize_sku(sku):
    sku = sku.strip()

    if not sku.lower().startswith(("standard_", "basic_")):
        sku = "Standard_" + sku

    return sku


@lru_cache(maxsize=1024)
def get_azure_monthly_price(sku_name, region_name):

    region = normalize_region(region_name)
    sku = normalize_sku(sku_name).lower()

    url = (
        BASE_URL
        + f"&$filter=serviceName eq 'Virtual Machines'"
        + f" and armRegionName eq '{region}'"
    )

    prices = {}

    while url:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        for item in data.get("Items", []):

            arm_sku = item.get("armSkuName", "").lower()

            if not arm_sku:
                continue

            retail = item.get("retailPrice")

            if retail is None:
                continue

            reservation = item.get("reservationTerm")
            price_type = item.get("priceType")

            monthly = None

            if reservation == "3 Years":
                monthly = round(retail / 36, 2)

            elif reservation == "1 Year":
                monthly = round(retail / 12, 2)

            elif price_type == "Consumption":
                monthly = round(retail * 730, 2)

            if monthly is None:
                continue

            # Keep the lowest monthly price
            if arm_sku not in prices or monthly < prices[arm_sku]:
                prices[arm_sku] = monthly

        url = data.get("NextPageLink")

    # ------------------------
    # Exact Match
    # ------------------------

    if sku in prices:
        return prices[sku]

    # ------------------------
    # Match without Standard_
    # ------------------------

    short = sku.replace("standard_", "")

    for key, value in prices.items():
        if key.replace("standard_", "") == short:
            return value

    # ------------------------
    # Fuzzy Match
    # ------------------------

    matches = difflib.get_close_matches(
        sku,
        prices.keys(),
        n=1,
        cutoff=0.80,
    )

    if matches:
        print(f"[Pricing] Using closest SKU: {matches[0]}")
        return prices[matches[0]]

    print(f"[Pricing] Price not found for {sku_name} ({region_name})")

    return 0.0