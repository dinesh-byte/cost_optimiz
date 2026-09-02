"""
Dynamic Azure VM SKU suggestion engine.

Requirements:
    pip install azure-identity requests

Authentication:
    Uses DefaultAzureCredential, so it works with:
      - az login
      - Managed Identity
      - Service Principal environment variables

Example:
    python suggestion.py \
        --subscription-id "<subscription-id>" \
        --region "eastus" \
        --sku "Standard_D16ds_v5" \
        --cpu-p95 25 \
        --memory-p95 30
"""

import argparse
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import requests
from azure.identity import DefaultAzureCredential


CPU_THRESHOLD = 40.0
MEMORY_THRESHOLD = 40.0

SKU_API = (
    "https://management.azure.com/subscriptions/"
    "{subscription_id}/providers/Microsoft.Compute/skus"
    "?api-version=2025-04-01"
)


@dataclass
class ParsedSKU:
    full_name: str
    family: str
    cores: int
    suffix: str
    version: str
    subfamily: str


def parse_sku(sku_name: str) -> Optional[ParsedSKU]:
    """
    Parse common Azure VM SKU names.

    Examples:
        Standard_D16ds_v5 -> family=D, cores=16, suffix=ds, version=5
        Standard_D8as_v5  -> family=D, cores=8,  suffix=as, version=5
        Standard_E16ds_v5 -> family=E, cores=16, suffix=ds, version=5
        Standard_F8s_v2   -> family=F, cores=8,  suffix=s,  version=2
    """
    pattern = re.compile(
        r"^Standard_"
        r"(?P<family>[A-Za-z]+?)"
        r"(?P<cores>\d+(?:-\d+)?)"
        r"(?P<suffix>[A-Za-z]*)"
        r"_v(?P<version>\d+)$",
        re.IGNORECASE,
    )

    match = pattern.match(sku_name)
    if not match:
        return None

    core_text = match.group("cores")
    # For sizes such as 16-4, use the first number as the primary core count.
    cores = int(core_text.split("-")[0])

    family = match.group("family")
    suffix = match.group("suffix")
    version = match.group("version")

    return ParsedSKU(
        full_name=sku_name,
        family=family.upper(),
        cores=cores,
        suffix=suffix.lower(),
        version=version,
        subfamily=f"{family.upper()}{suffix.lower()}",
    )


def get_access_token() -> str:
    credential = DefaultAzureCredential()
    token = credential.get_token(
        "https://management.azure.com/.default"
    )
    return token.token


def get_region_skus(
    subscription_id: str,
    region: str,
) -> List[dict]:
    """
    Fetch all Compute VM SKUs available to the subscription/region.
    Handles Azure API pagination.
    """
    token = get_access_token()

    url = SKU_API.format(subscription_id=subscription_id)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    results = []

    while url:
        response = requests.get(
            url,
            headers=headers,
            timeout=60,
        )
        response.raise_for_status()

        payload = response.json()
        results.extend(payload.get("value", []))
        url = payload.get("nextLink")

    region_normalized = region.lower().replace(" ", "")

    filtered = []

    for item in results:
        locations = [
            str(location).lower().replace(" ", "")
            for location in item.get("locations", [])
        ]

        if region_normalized in locations:
            filtered.append(item)

    return filtered


def capability_value(item: dict, capability_name: str) -> Optional[str]:
    for capability in item.get("capabilities", []):
        if capability.get("name", "").lower() == capability_name.lower():
            return capability.get("value")
    return None


def is_supported_sku(item: dict) -> bool:
    """
    Keep only normal VM SKUs that can be deployed.

    We exclude retired/not-available SKUs where Azure exposes a
    restrictive restriction entry.
    """
    restrictions = item.get("restrictions", [])

    for restriction in restrictions:
        reason = str(restriction.get("reasonCode", "")).lower()
        if reason in {
            "notavailableforsubscription",
            "quotaidnotavailable",
        }:
            return False

    return True


def sku_matches_subfamily(
    candidate: ParsedSKU,
    current: ParsedSKU,
) -> bool:
    """
    Match the VM family/subfamily exactly.

    D8ds_v5 -> Dds
    D8as_v5 -> Das
    E16ds_v5 -> Eds

    This prevents a Dds VM from silently becoming a Das/D-series VM.
    """
    return (
        candidate.family == current.family
        and candidate.suffix == current.suffix
        and candidate.version == current.version
    )


def get_memory_mb(item: dict) -> Optional[int]:
    value = capability_value(item, "MemoryGB")

    if value is None:
        return None

    try:
        return int(float(value) * 1024)
    except (TypeError, ValueError):
        return None


def get_vcpus(item: dict) -> Optional[int]:
    value = capability_value(item, "vCPUs")

    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_architecture(item: dict) -> Optional[str]:
    value = capability_value(item, "CpuArchitectureType")
    return value.lower() if value else None


def find_dynamic_suggestion(
    current_sku: str,
    region: str,
    region_skus: List[dict],
) -> Tuple[Optional[str], str]:
    """
    Find the next lower valid SKU dynamically from Azure's SKU API.

    Rules:
      1. Same family.
      2. Same subfamily/suffix.
      3. Same version/generation.
      4. Lower vCPU count.
      5. Prefer the immediate next lower vCPU count.
      6. Preserve architecture where Azure exposes it.
    """
    current = parse_sku(current_sku)

    if not current:
        return None, "Invalid Azure SKU format"

    if current.family == "F":
        return None, "F-series does not have a downsizing recommendation"

    current_item = None

    for item in region_skus:
        if item.get("name", "").lower() == current_sku.lower():
            current_item = item
            break

    current_arch = get_architecture(current_item) if current_item else None

    candidates = []

    for item in region_skus:
        if not is_supported_sku(item):
            continue

        name = item.get("name", "")

        if not name:
            continue

        parsed = parse_sku(name)

        if not parsed:
            continue

        if not sku_matches_subfamily(parsed, current):
            continue

        if parsed.cores >= current.cores:
            continue

        # If Azure exposes architecture, preserve it.
        candidate_arch = get_architecture(item)

        if current_arch and candidate_arch:
            if candidate_arch != current_arch:
                continue

        vcpus = get_vcpus(item)

        if vcpus is None:
            vcpus = parsed.cores

        if vcpus >= current.cores:
            continue

        candidates.append(
            {
                "name": name,
                "cores": parsed.cores,
                "vcpus": vcpus,
                "memory_mb": get_memory_mb(item),
            }
        )

    if not candidates:
        return None, (
            f"No lower SKU found in Azure for {current_sku} "
            f"in {region} with the same subfamily/version"
        )

    # Immediate lower SKU: largest core count below current.
    candidates.sort(
        key=lambda x: (x["cores"], x["memory_mb"] or 0),
        reverse=True,
    )

    selected = candidates[0]

    return selected["name"], (
        f"Dynamic Azure SKU match: {current_sku} -> "
        f"{selected['name']} ({selected['cores']} cores)"
    )


def suggest_sku(
    subscription_id: str,
    region: str,
    current_sku: str,
    cpu_p95: float,
    memory_p95: float,
) -> Dict:
    """
    Main recommendation function.
    """
    parsed = parse_sku(current_sku)

    if not parsed:
        return {
            "current_sku": current_sku,
            "suggested_sku": current_sku,
            "action": "Invalid SKU",
            "reason": "Unable to parse SKU",
        }

    if parsed.family == "F":
        return {
            "current_sku": current_sku,
            "suggested_sku": current_sku,
            "action": "No Change",
            "reason": "F-series does not have downsizing opportunity",
        }

    if cpu_p95 >= CPU_THRESHOLD or memory_p95 >= MEMORY_THRESHOLD:
        reasons = []

        if cpu_p95 >= CPU_THRESHOLD:
            reasons.append(
                f"CPU P95 {cpu_p95:.1f}% >= {CPU_THRESHOLD:.1f}%"
            )

        if memory_p95 >= MEMORY_THRESHOLD:
            reasons.append(
                f"Memory P95 {memory_p95:.1f}% >= {MEMORY_THRESHOLD:.1f}%"
            )

        return {
            "current_sku": current_sku,
            "suggested_sku": current_sku,
            "action": "No Change",
            "reason": " and ".join(reasons),
        }

    region_skus = get_region_skus(
        subscription_id=subscription_id,
        region=region,
    )

    suggested, reason = find_dynamic_suggestion(
        current_sku=current_sku,
        region=region,
        region_skus=region_skus,
    )

    if not suggested:
        return {
            "current_sku": current_sku,
            "suggested_sku": current_sku,
            "action": "No Change",
            "reason": reason,
        }

    return {
        "current_sku": current_sku,
        "suggested_sku": suggested,
        "action": "Downsize",
        "reason": (
            f"CPU P95 {cpu_p95:.1f}% and Memory P95 "
            f"{memory_p95:.1f}% are below thresholds. {reason}"
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Dynamic Azure VM SKU recommendation"
    )

    parser.add_argument("--subscription-id", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--sku", required=True)
    parser.add_argument("--cpu-p95", required=True, type=float)
    parser.add_argument("--memory-p95", required=True, type=float)

    args = parser.parse_args()

    result = suggest_sku(
        subscription_id=args.subscription_id,
        region=args.region,
        current_sku=args.sku,
        cpu_p95=args.cpu_p95,
        memory_p95=args.memory_p95,
    )

    print("\nAzure VM SKU Recommendation")
    print("-" * 70)

    for key, value in result.items():
        print(f"{key:18}: {value}")


if __name__ == "__main__":
    main()
  
