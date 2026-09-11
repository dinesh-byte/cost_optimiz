"""VM downsizing decision and SKU selection logic."""

from typing import Dict, List, Optional, Tuple

from sku_parser import ParsedSKU
from azure_sku import build_sku_objects


CPU_THRESHOLD = 40.0
MEMORY_THRESHOLD = 40.0


def determine_action(cpu_max: float, memory_max: float) -> str:
    """
    Determine which resource can be downsized.

    CPU < 40 and Memory < 40 -> Downsize Both
    CPU >= 40 and Memory < 40 -> Downsize Memory
    CPU < 40 and Memory >= 40 -> Downsize CPU
    CPU >= 40 and Memory >= 40 -> No Opportunity
    """
    cpu_low = cpu_max < CPU_THRESHOLD
    memory_low = memory_max < MEMORY_THRESHOLD

    if cpu_low and memory_low:
        return "Downsize Both"

    if not cpu_low and memory_low:
        return "Downsize Memory"

    if cpu_low and not memory_low:
        return "Downsize CPU"

    return "No Opportunity"


def architecture_matches(candidate: dict, current: dict) -> bool:
    current_arch = current.get("architecture")
    candidate_arch = candidate.get("architecture")

    if current_arch and candidate_arch:
        return current_arch == candidate_arch

    return True


def find_next_lower_same_family(
    current: ParsedSKU,
    current_item: dict,
    sku_objects: List[dict],
) -> Optional[dict]:
    """Find the immediate lower SKU in the same family/subfamily/version."""
    candidates = []

    for item in sku_objects:
        candidate = item["parsed"]

        if candidate.family != current.family:
            continue

        if candidate.suffix != current.suffix:
            continue

        if candidate.version != current.version:
            continue

        if candidate.cores >= current.cores:
            continue

        if not architecture_matches(item, current_item):
            continue

        candidates.append(item)

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: (
            x["cores"],
            x["memory_gb"] or 0,
        ),
        reverse=True,
    )

    return candidates[0]


def find_cross_family_suggestion(
    current: ParsedSKU,
    current_item: dict,
    sku_objects: List[dict],
) -> Optional[dict]:
    """
    Cross-family rules:

        D -> F : same cores
        E -> D : same cores
        D -> E : next lower core count
        F -> D : lower core count

    Version and suffix are preserved.
    """

    if current.family == "D":
        target_family = "F"
        mode = "same"

    elif current.family == "E":
        target_family = "D"
        mode = "same"

    elif current.family == "F":
        target_family = "D"
        mode = "lower"

    else:
        return None

    candidates = []

    for item in sku_objects:
        candidate = item["parsed"]

        if candidate.family != target_family:
            continue

        if candidate.version != current.version:
            continue

        if candidate.suffix != current.suffix:
            continue

        if not architecture_matches(item, current_item):
            continue

        if mode == "same" and candidate.cores != current.cores:
            continue

        if mode == "lower" and candidate.cores >= current.cores:
            continue

        candidates.append(item)

    if not candidates:
        return None

    if mode == "lower":
        candidates.sort(
            key=lambda x: (
                x["cores"],
                x["memory_gb"] or 0,
            ),
            reverse=True,
        )
    else:
        current_memory = current_item.get("memory_gb") or 0
        candidates.sort(
            key=lambda x: abs(
                (x["memory_gb"] or 0) - current_memory
            )
        )

    return candidates[0]


def find_resize_candidate(
    current_sku: str,
    region_skus: List[dict],
) -> Tuple[Optional[str], str]:
    """
    Select the best SKU according to the family rules.

    Priority:
        1. Same-family immediate lower SKU.
        2. Cross-family SKU.
    """
    from sku_parser import parse_sku

    current = parse_sku(current_sku)

    if not current:
        return None, "Invalid Azure SKU format"

    sku_objects = build_sku_objects(region_skus)

    current_item = next(
        (
            item for item in sku_objects
            if item["name"].lower() == current_sku.lower()
        ),
        None,
    )

    if current_item is None:
        return (
            None,
            f"Current SKU {current_sku} was not found "
            "in the Azure SKU list",
        )

    same_family = find_next_lower_same_family(
        current,
        current_item,
        sku_objects,
    )

    if same_family:
        return (
            same_family["name"],
            (
                f"Same-family resize: "
                f"{current_sku} -> {same_family['name']}"
            ),
        )

    cross_family = find_cross_family_suggestion(
        current,
        current_item,
        sku_objects,
    )

    if cross_family:
        return (
            cross_family["name"],
            (
                f"Cross-family resize: "
                f"{current_sku} -> {cross_family['name']}"
            ),
        )

    return (
        None,
        (
            f"No lower SKU found for {current_sku} "
            f"in version v{current.version} "
            "with the requested family rules"
        ),
    )


def suggest_sku(
    subscription_id: str,
    region: str,
    current_sku: str,
    cpu_max: float,
    memory_max: float,
) -> Dict:
    """Generate the complete VM downsizing recommendation."""
    from sku_parser import parse_sku
    from azure_sku import get_region_skus

    parsed = parse_sku(current_sku)

    if not parsed:
        return {
            "current_sku": current_sku,
            "suggested_sku": current_sku,
            "action": "Invalid SKU",
            "reason": "Unable to parse SKU",
        }

    action = determine_action(cpu_max, memory_max)

    if action == "No Opportunity":
        return {
            "current_sku": current_sku,
            "suggested_sku": current_sku,
            "action": action,
            "cpu_max": f"{cpu_max:.1f}%",
            "memory_max": f"{memory_max:.1f}%",
            "reason": (
                f"CPU Max {cpu_max:.1f}% >= {CPU_THRESHOLD:.1f}% "
                f"and Memory Max {memory_max:.1f}% >= "
                f"{MEMORY_THRESHOLD:.1f}%"
            ),
        }

    region_skus = get_region_skus(
        subscription_id=subscription_id,
        region=region,
    )

    suggested, sku_reason = find_resize_candidate(
        current_sku=current_sku,
        region_skus=region_skus,
    )

    if not suggested:
        return {
            "current_sku": current_sku,
            "suggested_sku": current_sku,
            "action": "No Opportunity",
            "cpu_max": f"{cpu_max:.1f}%",
            "memory_max": f"{memory_max:.1f}%",
            "reason": sku_reason,
        }

    return {
        "current_sku": current_sku,
        "suggested_sku": suggested,
        "action": action,
        "cpu_max": f"{cpu_max:.1f}%",
        "memory_max": f"{memory_max:.1f}%",
        "reason": (
            f"CPU Max {cpu_max:.1f}% / "
            f"Memory Max {memory_max:.1f}%. "
            f"{sku_reason}"
        ),
    }
