
import argparse
import csv
import logging
from collections import defaultdict

from suggestion import (
    load_vm_series_reference,
    compute_sku_suggestion,
)

from cost_cal import get_azure_monthly_price
from mail import send_vm_report_email, RECEIVER_EMAIL


# ----------------------------------------------------
# Configuration
# ----------------------------------------------------

CPU_THRESHOLD = 40.0
MEMORY_THRESHOLD = 40.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


# ----------------------------------------------------
# Helpers
# ----------------------------------------------------

def normalize_row(row):
    """
    Remove spaces/underscores and lowercase column names.
    """
    return {
        str(k).replace(" ", "").replace("_", "").lower().strip(): v
        for k, v in row.items()
        if k
    }


def to_float(value):
    """
    Safely convert CSV values to float.
    """
    try:
        return float(str(value).replace("%", "").strip())
    except Exception:
        return 0.0


# ----------------------------------------------------
# Core Logic
# ----------------------------------------------------

def process_csv(
        csv_file,
        cpu_threshold=CPU_THRESHOLD,
        memory_threshold=MEMORY_THRESHOLD
):
    """
    Reads the CSV and groups recommendations by owner email.
    Supports basic utilization tables and aggregated metrics sheets.
    """
    vm_reference = load_vm_series_reference()
    owner_groups = defaultdict(list)

    with open(csv_file, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            row = normalize_row(row)

            # Support both layout types: 'vmname' or 'vmname' with space
            vm_name = (row.get("vmname") or row.get("vmname")).strip()

            if not vm_name:
                continue

            # Strip out "Standard_" prefix uniformly for the engine logic
            current_sku = row.get("currentsku", "").replace(
                "Standard_", ""
            ).strip()

            region = row.get("region", "").strip()

            owner = row.get(
                "appownermailid",
                RECEIVER_EMAIL
            ).strip().lower()

            # Dynamic metric mapping: prioritize P95/Avg metrics if available
            avg_cpu = to_float(row.get("averagecpu"))
            p95_cpu = to_float(row.get("p95cpu"))
            peak_cpu = to_float(row.get("peakcpu"))

            avg_memory = to_float(row.get("averagememory"))
            p95_memory = to_float(row.get("p95memory"))
            peak_memory = to_float(row.get("peakmemory"))

            # Use P95 for recommendation logic
            cpu = p95_cpu if p95_cpu else avg_cpu
            memory = p95_memory if p95_memory else avg_memory

            # Skip healthy or heavily utilized VMs
            if cpu >= cpu_threshold and memory >= memory_threshold:
                continue

            suggested_sku, reason = compute_sku_suggestion(
                current_sku,
                cpu,
                memory,
                vm_reference,
            )

            if suggested_sku.replace("Standard_", "") == current_sku:
                recommendation = "Keep Current Size"
            else:
                recommendation = "Downsize"


            logger.info(
                "Processing %s (%s -> %s)",
                vm_name,
                current_sku,
                suggested_sku,
            )

            current_price = get_azure_monthly_price(
                current_sku,
                region,
            )

            suggested_price = get_azure_monthly_price(
                suggested_sku,
                region,
            )
            

            savings = max(
                0,
                current_price - suggested_price
            )

            owner_groups[owner].append(
                {
                    "vmname": vm_name,
                    "region": region,

                    "currentsku": (
                        f"Standard_{current_sku}"
                        if not current_sku.startswith("Standard_")
                        else current_sku
                    ),

                    "suggestedsku": (
                        suggested_sku
                        if suggested_sku.startswith("Standard_")
                        else f"Standard_{suggested_sku}"
                    ),

                    "avg_cpu": avg_cpu,
                    "p95_cpu": p95_cpu,
                    "peak_cpu": peak_cpu,

                    "avg_memory": avg_memory,
                    "p95_memory": p95_memory,
                    "peak_memory": peak_memory,

                    "current_cost": current_price,
                    "suggested_cost": suggested_price,
                    "monthly_savings": savings,

                    "recommendation": recommendation,
                    "reason": reason,
                }
            )

    return owner_groups


# ----------------------------------------------------
# Email Reports
# ----------------------------------------------------

# def send_reports(owner_groups, cpu_threshold=CPU_THRESHOLD, memory_threshold=MEMORY_THRESHOLD):

#     if not owner_groups:
#         logger.info("No underutilized VMs found.")
#         return

#     logger.info("Sending reports...")

#     for owner, vm_list in owner_groups.items():
#         logger.info(
#             "Sending %d VM recommendations to %s",
#             len(vm_list),
#             owner,
#         )

#         send_vm_report_email(
#             vm_list=vm_list,
#             receiver_email=owner,
#             cpu_threshold=cpu_threshold,
#             mem_threshold=memory_threshold,
#         )


# ----------------------------------------------------
# Main
# ----------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Azure VM Rightsizing Recommendation Tool"
    )

    parser.add_argument(
        "csv_file",
        help="Path to VM utilization CSV",
    )

    parser.add_argument(
        "--cpu",
        type=float,
        default=CPU_THRESHOLD,
        help="CPU threshold (evaluates P95, Avg, or Real-time logs)",
    )

    parser.add_argument(
        "--memory",
        type=float,
        default=MEMORY_THRESHOLD,
        help="Memory threshold (evaluates P95, Avg, or Real-time logs)",
    )

    args = parser.parse_args()

    logger.info("Reading CSV: %s", args.csv_file)

    owner_groups = process_csv(
        args.csv_file,
        args.cpu,
        args.memory,
    )

    logger.info(
        "Found recommendations for %d owner(s)",
        len(owner_groups),
    )
    logger.info("=" * 180)
    logger.info(
        "%-15s %-20s %-10s %-10s %-10s %-10s %-18s %-18s %-12s %-12s %-12s %-12s %-15s",
        "VM Name",
        "Owner",
        "CPU(P95)",
        "MEM(P95)",
        "Current SKU",
        "Suggested",
        "Current Cost",
        "Suggested Cost",
        "Savings",
        "Action",
        "Region",
        "Reason",
        "Recommendation",
    )
    logger.info("=" * 180)

    for owner, vm_list in owner_groups.items():
        for vm in vm_list:
            logger.info(
                "%-15s %-20s %-10.2f %-10.2f %-18s %-18s $%-11.2f $%-11.2f $%-11.2f %-12s %-12s %-15s %-20s",
                vm["vmname"],
                owner,
                vm["p95_cpu"] if vm["p95_cpu"] else vm["avg_cpu"],
                vm["p95_memory"] if vm["p95_memory"] else vm["avg_memory"],
                vm["currentsku"],
                vm["suggestedsku"],
                vm["current_cost"],
                vm["suggested_cost"],
                vm["monthly_savings"],
                vm["recommendation"],
                vm["region"],
                vm["reason"][:15],
                vm["recommendation"],
            )


    # send_reports(
    #     owner_groups,
    #     cpu_threshold=args.cpu,
    #     memory_threshold=args.memory
    # )



if __name__ == "__main__":
    main()
