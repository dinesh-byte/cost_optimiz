# ##file name cost_cal.py
# import requests
# import json

# api_url = (
#     "https://prices.azure.com/api/retail/prices"
#     "?api-version=2023-01-01-preview"
#     "&$filter=armRegionName eq 'westeurope' "
#     "and armSkuName eq 'Standard_E32-16s_v4'"
# )

# result = []

# while api_url:
#     response = requests.get(api_url)
#     response.raise_for_status()

#     data = response.json()

#     for item in data.get("Items", []):
#         if item.get("reservationTerm") == "3 Years":
#             total_price = item.get("retailPrice", 0)
#             monthly_price = round(total_price / 36, 2)

#             result.append({
#                 "sku": item.get("armSkuName"),
#                 "region": item.get("armRegionName"),
#                 "term": item.get("reservationTerm"),
#                 "monthlyPrice": monthly_price,
#                 "currency": item.get("currencyCode"),
#             })

#     api_url = data.get("NextPageLink")

# print(json.dumps(result, indent=4))
    
#version 2.-
# """
# cost_cal.py

# Azure Retail Pricing API helper

# Fetches Azure VM monthly prices with caching.
# Supports:
#     - 3-Year Reserved Price (preferred)
#     - 1-Year Reserved Price (fallback)
#     - Consumption Price (fallback)

# Author: Dinesh
# """

# import requests
# from functools import lru_cache

# API_VERSION = "2023-01-01-preview"

# BASE_URL = (
#     f"https://prices.azure.com/api/retail/prices"
#     f"?api-version={API_VERSION}"
# )

# HEADERS = {
#     "User-Agent": "AzureVMRightsizer/1.0",
#     "Accept": "application/json"
# }

# # Region Mapping
# REGION_MAP = {
#     "East US": "eastus",
#     "East US 2": "eastus2",
#     "West US": "westus",
#     "West US 2": "westus2",
#     "West US 3": "westus3",
#     "Central US": "centralus",
#     "North Europe": "northeurope",
#     "West Europe": "westeurope",
#     "Southeast Asia": "southeastasia",
#     "South India": "southindia",
#     "Central India": "centralindia",
#     "West India": "westindia",
# }


# def normalize_region(region):
#     """
#     Convert Azure display name to armRegionName.
#     """

#     if not region:
#         return ""

#     return REGION_MAP.get(
#         region.strip(),
#         region.strip().lower().replace(" ", "")
#     )


# def normalize_sku(sku):
#     """
#     Ensure Standard_ prefix.
#     """

#     sku = sku.strip()

#     if not sku.lower().startswith(("standard_", "basic_")):
#         sku = "Standard_" + sku

#     return sku


# @lru_cache(maxsize=1024)
# def get_azure_monthly_price(sku_name, region_name):
#     """
#     Returns monthly VM price.

#     Preference order:

#     1. Reserved 3 Years
#     2. Reserved 1 Year
#     3. Consumption
#     """

#     sku = normalize_sku(sku_name)
#     region = normalize_region(region_name)

#     url = (
#         BASE_URL
#         + f"&$filter=serviceName eq 'Virtual Machines'"
#         + f" and armRegionName eq '{region}'"
#         + f" and armSkuName eq '{sku}'"
#     )

#     reserved3 = None
#     reserved1 = None
#     consumption = None

#     try:

#         while url:

#             response = requests.get(
#                 url,
#                 headers=HEADERS,
#                 timeout=20
#             )

#             response.raise_for_status()

#             data = response.json()

#             for item in data.get("Items", []):

#                 price = item.get("retailPrice")

#                 if price is None:
#                     continue

#                 price_type = item.get("priceType", "")
#                 reservation = item.get("reservationTerm")

#                 # 3 Year Reserved
#                 if reservation == "3 Years":
#                     reserved3 = round(price / 36, 2)

#                 # 1 Year Reserved
#                 elif reservation == "1 Year":
#                     reserved1 = round(price / 12, 2)

#                 # Pay As You Go
#                 elif price_type == "Consumption":

#                     # retailPrice is hourly

#                     consumption = round(price * 730, 2)

#             url = data.get("NextPageLink")

#         if reserved3 is not None:
#             return reserved3

#         if reserved1 is not None:
#             return reserved1

#         if consumption is not None:
#             return consumption

#     except requests.RequestException as ex:

#         print(
#             f"Pricing lookup failed "
#             f"[{sku}] [{region}] : {ex}"
#         )

#     return 0.0


# if __name__ == "__main__":

#     tests = [
#         ("Standard_D8ds_v5", "East US"),
#         ("Standard_F16s_v2", "Southeast Asia"),
#         ("Standard_E4ds_v5", "North Europe"),
#     ]

#     for sku, region in tests:

#         price = get_azure_monthly_price(sku, region)

#         print(
#             f"{sku:<25}"
#             f"{region:<20}"
#             f"${price:.2f}/month"
#         )


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