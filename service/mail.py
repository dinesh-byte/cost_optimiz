

"""
mail.py

Email Service for Azure VM Rightsizing Report
"""



import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ==========================================================
# SMTP Configuration
# ==========================================================

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

#SENDER_EMAIL = os.getenv("SENDER_EMAIL")
#SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
SENDER_EMAIL = "dineshvenkartr05@gmail.com"
SENDER_PASSWORD = ""  # Runtime app password verification token

# Default receiver if owner email is missing
RECEIVER_EMAIL = os.getenv("DEFAULT_RECEIVER_EMAIL", "dineshkumar90885@gmail.com")


from datetime import datetime

def build_html_report(vm_list, cpu_threshold, mem_threshold):

    total_current = sum(vm["current_cost"] for vm in vm_list)
    total_new = sum(vm["suggested_cost"] for vm in vm_list)
    total_savings = sum(vm["monthly_savings"] for vm in vm_list)

    annual_savings = total_savings * 12

    generated = datetime.now().strftime("%d-%b-%Y %H:%M")

    html = f"""
<html>

<head>

<style>

body {{
    font-family:Segoe UI,Arial;
    margin:20px;
}}

h2 {{
    color:#0d6efd;
}}

.summary {{
    background:#f4f8ff;
    padding:15px;
    border-left:5px solid #0d6efd;
    margin-bottom:20px;
}}

table {{
    border-collapse:collapse;
    width:100%;
    font-size:13px;
}}

th {{
    background:#0d6efd;
    color:white;
    padding:10px;
    border:1px solid #ddd;
}}

td {{
    border:1px solid #ddd;
    padding:8px;
    text-align:center;
}}

tr:nth-child(even){{
    background:#f8f8f8;
}}

.current{{
    color:#d60000;
    font-weight:bold;
}}

.suggested{{
    color:#008000;
    font-weight:bold;
}}

.money{{
    color:#006400;
    font-weight:bold;
}}

.high {{
    background:#d4edda;
    color:#155724;
    font-weight:bold;
}}

.medium {{
    background:#fff3cd;
    color:#856404;
    font-weight:bold;
}}

.low {{
    background:#f8d7da;
    color:#721c24;
    font-weight:bold;
}}

.downsize {{
    color:green;
    font-weight:bold;
}}

.keep {{
    color:red;
    font-weight:bold;
}}

.rules {{
    margin-top:25px;
    background:#fafafa;
    padding:15px;
    border:1px solid #ddd;
}}

.footer {{
    margin-top:20px;
    font-size:12px;
    color:#555;
}}

</style>

</head>

<body>

<h2>Azure VM Rightsizing Recommendation Report</h2>

<div class="summary">

<b>Assessment Period:</b> Last 30 Days<br>
<b>Generated On:</b> {generated}<br>
<b>CPU Threshold:</b> {cpu_threshold}%<br>
<b>Memory Threshold:</b> {mem_threshold}%<br>
<b>Total Underutilized VMs:</b> {len(vm_list)}<br><br>

<b>Current Monthly Cost:</b> ${total_current:.2f}<br>
<b>Projected Monthly Cost:</b> ${total_new:.2f}<br>
<b>Monthly Savings:</b> <span style="color:green;"><b>${total_savings:.2f}</b></span><br>
<b>Annual Savings:</b> <span style="color:green;"><b>${annual_savings:.2f}</b></span>

</div>

<table>

<tr>

<th>#</th>
<th>VM</th>

<th>Current SKU</th>
<th>Suggested SKU</th>

<th>Avg CPU</th>
<th>P95 CPU</th>
<th>Peak CPU</th>

<th>Avg Mem</th>
<th>P95 Mem</th>
<th>Peak Mem</th>

<th>Current Cost</th>
<th>Suggested Cost</th>
<th>Savings</th>

<th>Recommendation</th>
<th>Reason</th>

</tr>
"""

    for i, vm in enumerate(vm_list, 1):

       

        recommendation = vm["recommendation"]

        rec_class = "keep"

        if "Downsize" in recommendation:
            rec_class = "downsize"

        html += f"""

<tr>

<td>{i}</td>

<td>{vm['vmname']}</td>

<td class="current">{vm['currentsku']}</td>

<td class="suggested">{vm['suggestedsku']}</td>

<td>{vm['avg_cpu']:.1f}%</td>
<td>{vm['p95_cpu']:.1f}%</td>
<td>{vm['peak_cpu']:.1f}%</td>

<td>{vm['avg_memory']:.1f}%</td>
<td>{vm['p95_memory']:.1f}%</td>
<td>{vm['peak_memory']:.1f}%</td>

<td>${vm['current_cost']:.2f}</td>

<td>${vm['suggested_cost']:.2f}</td>

<td class="money">${vm['monthly_savings']:.2f}</td>


<td class="{rec_class}">{vm['recommendation']}</td>

<td>{vm['reason']}</td>

</tr>

"""

    html += """

</table>

<div class="rules">

<h3>Rightsizing Rules Used</h3>

<ul>

<li>CPU P95 &lt; 20% and Memory P95 &lt; 40% → Downsize 2 Levels</li>

<li>CPU P95 &lt; 35% and Memory P95 &lt; 50% → Downsize 1 Level</li>

<li>Peak CPU ≥ 85% → No Recommendation</li>

<li>Memory P95 ≥ 80% → No Recommendation</li>

<li>Recommendation should always be validated before production implementation.</li>

</ul>

</div>

<div class="footer">

This report is generated automatically using Azure VM inventory,
New Relic performance metrics and Azure Retail Pricing API.

Please validate application workload, CPU spikes,
memory utilization, storage IOPS and network throughput before resizing production VMs.

</div>

</body>

</html>

"""

    return html

# ==========================================================
# Send Email
# ==========================================================

def send_vm_report_email(
        vm_list,
        cpu_threshold=40,
        mem_threshold=40,
        receiver_email=None,
):
    """
    Sends VM recommendation report.
    """

    if not receiver_email:
        receiver_email = RECEIVER_EMAIL

    if not vm_list:
        print(f"No recommendations for {receiver_email}")
        return

    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print("SMTP credentials are missing.")
        return

    subject = f"Azure VM Rightsizing Report ({len(vm_list)} VM(s))"

    html = build_html_report(
        vm_list,
        cpu_threshold,
        mem_threshold,
    )

    message = MIMEMultipart("alternative")

    message["Subject"] = subject
    message["From"] = SENDER_EMAIL
    message["To"] = receiver_email

    message.attach(MIMEText(html, "html"))

    try:

        context = ssl.create_default_context()

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:

            server.starttls(context=context)

            server.login(
                SENDER_EMAIL,
                SENDER_PASSWORD,
            )

            server.sendmail(
                SENDER_EMAIL,
                receiver_email,
                message.as_string(),
            )

        print(f"Email sent successfully to {receiver_email}")

    except Exception as ex:

        print(f"Unable to send email to {receiver_email}")

        print(ex)





        