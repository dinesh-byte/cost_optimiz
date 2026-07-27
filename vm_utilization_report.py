# """
# vm_utilization_report.py

# Reads a CSV file with columns: vmname, cpu utilization, memory utilization
# Filters VMs where BOTH CPU and Memory utilization are below a threshold
# (default 40%), and emails the filtered list as a report.

# Usage:
#     python vm_utilization_report.py path/to/vms.csv
# """

# import csv
# import sys

# from mail import send_vm_report_email, RECEIVER_EMAIL

# # Threshold for "underutilized"
# CPU_THRESHOLD = 40.0
# MEM_THRESHOLD = 40.0


# def read_and_filter_vms(csv_file_path, cpu_threshold=CPU_THRESHOLD, mem_threshold=MEM_THRESHOLD):
#     """
#     Reads the CSV file and returns a list of dicts for VMs where
#     cpu utilization < cpu_threshold AND memory utilization < mem_threshold.

#     Expected CSV headers (case-insensitive, spaces allowed):
#         vmname, cpu utilization, memory utilization
#     """
#     underutilized_vms = []

#     with open(csv_file_path, mode="r", newline="", encoding="utf-8-sig") as f:
#         reader = csv.DictReader(f)

#         # FIX: Safe header normalization that ignores None/empty trailing columns
#         normalized_fieldnames = {}
#         if reader.fieldnames:
#             for name in reader.fieldnames:
#                 if name:  # Skip empty or None headers
#                     normalized_fieldnames[name] = name.strip().lower()

#         for row in reader:
#             # FIX: Create normalized row safely, skipping keys that aren't mapped
#             norm_row = {}
#             for k, v in row.items():
#                 if k in normalized_fieldnames:
#                     norm_row[normalized_fieldnames[k]] = v

#             try:
#                 vm_name = norm_row.get("vmname", "").strip()
                
#                 # Strip out percentage signs and white spaces safely
#                 cpu_raw = norm_row.get("cpu utilization", "0")
#                 mem_raw = norm_row.get("memory utilization", "0")
                
#                 cpu_util = float(str(cpu_raw).strip().replace("%", "")) if cpu_raw else 0.0
#                 mem_util = float(str(mem_raw).strip().replace("%", "")) if mem_raw else 0.0
                
#             except (ValueError, AttributeError):
#                 # Skip rows with malformed numeric data
#                 continue

#             # Skip row if VM name is completely blank
#             if not vm_name:
#                 continue

#             if cpu_util < cpu_threshold and mem_util < mem_threshold:
#                 underutilized_vms.append({
#                     "vmname": vm_name,
#                     "cpu_utilization": cpu_util,
#                     "memory_utilization": mem_util,
#                 })

#     return underutilized_vms


# def process_vm_report(csv_file_path, cpu_threshold=CPU_THRESHOLD, mem_threshold=MEM_THRESHOLD,
#                        receiver_email=RECEIVER_EMAIL):
#     """
#     Main entry point: reads CSV, filters underutilized VMs, and emails the plain-text report.
#     """
#     underutilized_vms = read_and_filter_vms(csv_file_path, cpu_threshold, mem_threshold)

#     print(f"Found {len(underutilized_vms)} underutilized VM(s):")
#     for vm in underutilized_vms:
#         print(f"  {vm['vmname']} - CPU: {vm['cpu_utilization']}%, Memory: {vm['memory_utilization']}%")

#     # This calls the updated plain-text version of your mail.py script
#     send_vm_report_email(underutilized_vms, cpu_threshold, mem_threshold, receiver_email)

#     return underutilized_vms


# if __name__ == "__main__":
#     if len(sys.argv) != 2:
#         print("Usage: python vm_utilization_report.py <path_to_csv>")
#         sys.exit(1)

#     csv_path = sys.argv[1]
#     process_vm_report(csv_path)


import csv
import sys

from mail import send_vm_report_email, RECEIVER_EMAIL
from suggestion import load_vm_series_reference, compute_sku_suggestion

CPU_THRESHOLD = 40.0
MEM_THRESHOLD = 40.0

def read_and_filter_vms(csv_file_path, cpu_threshold=CPU_THRESHOLD, mem_threshold=MEM_THRESHOLD):
    underutilized_vms = []
    vm_families = load_vm_series_reference()

    try:
        with open(csv_file_path, mode="r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            normalized_fieldnames = {}
            if reader.fieldnames:
                for name in reader.fieldnames:
                    if name:
                        normalized_fieldnames[name] = name.strip().lower()

            for row in reader:
                norm_row = {}
                for k, v in row.items():
                    if k in normalized_fieldnames:
                        norm_row[normalized_fieldnames[k]] = v

                try:
                    vm_name = norm_row.get("vmname", "").strip()
                    cpu_raw = norm_row.get("cpu utilization", "0")
                    mem_raw = norm_row.get("memory utilization", "0")
                    current_sku = norm_row.get("currentsku", "").strip()
                    
                    cpu_util = float(str(cpu_raw).strip().replace("%", "")) if cpu_raw else 0.0
                    mem_util = float(str(mem_raw).strip().replace("%", "")) if mem_raw else 0.0
                    
                except (ValueError, AttributeError):
                    continue

                if not vm_name:
                    continue

                # Rule Filter Check: Catches VMs if EITHER or BOTH values drop beneath 40% threshold
                if cpu_util < cpu_threshold or mem_util < mem_threshold:
                    # Dynamically calculate sizes using suggestion module matrix
                    suggested_sku, reason = compute_sku_suggestion(
                        current_sku, cpu_util, mem_util, vm_families
                    )
                    
                    underutilized_vms.append({
                        "vmname": vm_name,
                        "cpu_utilization": cpu_util,
                        "memory_utilization": mem_util,
                        "currentsku": current_sku or "UNKNOWN",
                        "suggestedsku": suggested_sku,
                        "reason": reason
                    })
                    
    except FileNotFoundError:
        print(f"Error: The target file '{csv_file_path}' could not be located.")
        sys.exit(1)

    return underutilized_vms

def process_vm_report(csv_file_path, cpu_threshold=CPU_THRESHOLD, mem_threshold=MEM_THRESHOLD,
                       receiver_email=RECEIVER_EMAIL):
    underutilized_vms = read_and_filter_vms(csv_file_path, cpu_threshold, mem_threshold)

    print(f"Processed {len(underutilized_vms)} target optimization opportunities:")
    send_vm_report_email(underutilized_vms, cpu_threshold, mem_threshold, receiver_email)
    return underutilized_vms

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python vm_utilization_report.py <path_to_csv>")
        sys.exit(1)

    csv_path = sys.argv[1] # Patched index error target
    process_vm_report(csv_path)
