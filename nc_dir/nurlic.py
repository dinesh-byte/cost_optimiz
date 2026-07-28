import requests

API_KEY = "YOUR_NEW_RELIC_USER_API_KEY"
ACCOUNT_ID = 1234567

query = f"""
{{
  actor {{
    account(id:{ACCOUNT_ID}) {{
      nrql(
        query: "FROM SystemSample
                SELECT average(cpuPercent),
                       percentile(cpuPercent,95),
                       max(cpuPercent),
                       average(memoryUsedPercent),
                       percentile(memoryUsedPercent,95),
                       max(memoryUsedPercent)
                FACET hostname
                SINCE 30 days ago
                LIMIT MAX"
      ) {{
        results
      }}
    }}
  }}
}}
"""

response = requests.post(
    "https://api.newrelic.com/graphql",
    headers={
        "API-Key": API_KEY,
        "Content-Type": "application/json"
    },
    json={"query": query}
)

results = response.json()["data"]["actor"]["account"]["nrql"]["results"]

for vm in results:
    print(vm)