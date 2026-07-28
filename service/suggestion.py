import json
import os
import re


# ---------------------------------------------------------
# Load VM Reference
# ---------------------------------------------------------

def load_vm_series_reference():
    """
    Load Azure VM SKU reference JSON.

    Expected format:
    {
        "vm_families": [
            {
                "family": "D",
                "series_list": [
                    {
                        "name": "Dv5",
                        "skus": [
                            "D2ds_v5",
                            "D4ds_v5",
                            ...
                        ]
                    }
                ]
            }
        ]
    }
    """

    file_name = "azure_vm_series.json"

    if not os.path.exists(file_name):
        print(f"{file_name} not found.")
        return []

    with open(file_name, encoding="utf-8") as f:
        data = json.load(f)

    return data.get("vm_families", [])

# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------

def find_same_family_lower(families, family, version, current_sku):
    skus = get_family_skus(families, family, version)

    current = current_sku.replace("Standard_", "").lower()

    for i, (_, sku) in enumerate(skus):
        if sku.lower() == current:
            if i == 0:
                return current_sku
            return skus[i - 1][1]

    return current_sku


def find_same_core(families, family, version, cores):
    skus = get_family_skus(families, family, version)

    for c, sku in skus:
        if c == cores:
            return sku

    return None


def find_lower_core(families, family, version, cores):
    skus = get_family_skus(families, family, version)

    candidate = None

    for c, sku in skus:
        if c < cores:
            candidate = sku

    return candidate


# ---------------------------------------------------------
# SKU Parsing
# ---------------------------------------------------------

SKU_PATTERN = re.compile(
    r"^(?:Standard_)?([A-Za-z]+)(\d+(?:-\d+)?)([A-Za-z]*)(?:(_v\d+))?$",
    re.IGNORECASE,
)


def parse_sku_parts(sku):
    """
    Example:

    Standard_D8ds_v5

    Returns

    {
        family : D
        cores : 8
        suffix : ds
        version : _v5
    }
    """

    if not sku:
        return None

    sku = sku.replace("Standard_", "")

    match = SKU_PATTERN.match(sku)

    if not match:
        return None

    family, cores, suffix, version = match.groups()

    try:
        core_number = int(cores.split("-")[0])
    except Exception:
        core_number = 1

    return {
        "family": family.upper(),
        "cores": core_number,
        "suffix": suffix,
        "version": version or "",
    }


# ---------------------------------------------------------
# Get Ordered SKUs
# ---------------------------------------------------------

def get_family_skus(vm_families, family, version):
    """
    Returns all SKUs belonging to the same family/version.
    """

    result = []

    for group in vm_families:

        for series in group.get("series_list", []):

            for sku in series.get("skus", []):

                parsed = parse_sku_parts(sku)

                if not parsed:
                    continue

                if (
                    parsed["family"] == family
                    and parsed["version"] == version
                ):

                    result.append(
                        (
                            parsed["cores"],
                            sku
                        )
                    )

    result.sort(key=lambda x: x[0])

    return result


# ---------------------------------------------------------
# Recommendation Decision
# ---------------------------------------------------------

def determine_action(cpu, memory):
    

    if cpu < 40 and memory < 40:
        return "DOWNSIZE_BOTH"

    if cpu < 40:
        return "DOWNSIZE_CPU"

    if memory < 40:
        return "DOWNSIZE_MEMORY"

    return "NO_ACTION"


# ---------------------------------------------------------
# Recommendation Engine
# ---------------------------------------------------------

def compute_sku_suggestion(
    current_sku,
    cpu,
    memory,
    vm_families,
):

    action = determine_action(cpu, memory)

    if action == "NO_ACTION":
        return current_sku, "Healthy VM"

    parsed = parse_sku_parts(current_sku)

    if not parsed:
        return current_sku, "Unable to parse SKU"

    family = parsed["family"]
    cores = parsed["cores"]
    version = parsed["version"]

    # -------------------------------------------------
    # BOTH CPU & MEMORY LOW
    # -------------------------------------------------

    if action == "DOWNSIZE_BOTH":

        target = find_same_family_lower(
            vm_families,
            family,
            version,
            current_sku,
        )

        return target, "CPU & Memory utilization below threshold"

    # -------------------------------------------------
    # MEMORY LOW
    # CPU HIGH
    # -------------------------------------------------

    if action == "DOWNSIZE_MEMORY":

        if family == "D":

            target = find_same_core(
                vm_families,
                "F",
                version,
                cores,
            )

            if target:
                return target, "Move to F-Series (same cores)"

        elif family == "E":

            target = find_same_core(
                vm_families,
                "D",
                version,
                cores,
            )

            if target:
                return target, "Move to D-Series (same cores)"

        elif family == "F":

            return current_sku, "No opportunity"

    # -------------------------------------------------
    # CPU LOW
    # MEMORY HIGH
    # -------------------------------------------------

    if action == "DOWNSIZE_CPU":

        if family == "D":

            target = find_lower_core(
                vm_families,
                "E",
                version,
                cores,
            )

            if target:
                return target, "Move to E-Series (lower cores)"

        elif family == "F":

            target = find_lower_core(
                vm_families,
                "D",
                version,
                cores,
            )

            if target:
                return target, "Move to D-Series (lower cores)"

        elif family == "E":

            return current_sku, "No opportunity"

    return current_sku, "No recommendation"

# ---------------------------------------------------------
# Standalone Test
# ---------------------------------------------------------

if __name__ == "__main__":

    families = load_vm_series_reference()

    samples = [

        ("Standard_D8ds_v5", 20, 15),

        ("Standard_D16plds_v6", 18, 17),

        ("Standard_E8ds_v5", 30, 55),

        ("Standard_F16s_v2", 55, 25),

    ]

    for sku, cpu, mem in samples:

        suggested, reason = compute_sku_suggestion(
            sku,
            cpu,
            mem,
            families,
        )

        print("-" * 60)
        print("Current SKU :", sku)
        print("CPU         :", cpu)
        print("Memory      :", mem)
        print("Suggested   :", suggested)
        print("Reason      :", reason)