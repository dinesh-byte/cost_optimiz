##file name cost_cal.py
import requests
import json

api_url = (
    "https://prices.azure.com/api/retail/prices"
    "?api-version=2023-01-01-preview"
    "&$filter=armRegionName eq 'westeurope' "
    "and armSkuName eq 'Standard_D16v5'"
)

result = []

while api_url:
    response = requests.get(api_url)
    response.raise_for_status()

    data = response.json()

    for item in data.get("Items", []):
        if item.get("reservationTerm") == "3 Years":
            total_price = item.get("retailPrice", 0)
            monthly_price = round(total_price / 36, 2)

            result.append({
                "sku": item.get("armSkuName"),
                "region": item.get("armRegionName"),
                "term": item.get("reservationTerm"),
                "monthlyPrice": monthly_price,
                "currency": item.get("currencyCode"),
            })

    api_url = data.get("NextPageLink")

print(json.dumps(result, indent=4))