# Veeam Service Provider Console (VSPC) to Zabbix Integration

This project provides a Python script to monitor **Veeam Backup & Replication jobs** and **Veeam Agent jobs** (both managed and standalone) from the **Veeam Service Provider Console (VSPC)** and send the status to **Zabbix** using Zabbix Sender.

## Features

- **Auto-Discovery (LLD):** Automatically discovers all jobs (VM, Agent, File Share, etc.) in Zabbix.
- **Job Status Monitoring:** Reports the status (`Success`, `Warning`, `Failed`, `NotRun`) for each job.
- **Global Counters:** Tracks total Success, Warning, Failed, and Total jobs counts per execution.
- **Efficient:** Uses VSPC REST API v3 to fetch data and Zabbix Trapper for efficient data pushing.

## Prerequisites

- **Python 3.6+**
- **Zabbix Server** or Proxy (Version 6.0+ recommended)
- **Veeam Service Provider Console (VSPC) v9.1** or higher
- **REST API enabled** in VSPC (Check Configuration > Security > REST API)

### Python Dependencies
Install the required python libraries:
```bash
pip install requests pyzabbix urllib3
```

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-repo/vspc-zabbix.git
   cd vspc-zabbix
   ```

2. **Configure the script:**
   Open `vspc_zabbix.py` and edit the configuration section:

   ```python
   # --- VSPC CONFIGURATION ---
   BASE_URL = "https://vspc.your-domain.com/api/v3"
   USERNAME = "your-api-user"
   PASSWORD = "your-api-password"

   # --- ZABBIX CONFIGURATION ---
   ZABBIX_SERVER_IP = "127.0.0.1"   # IP of your Zabbix Server/Proxy
   ZABBIX_HOST_NAME = "VSPC-Monitor" # Hostname matching the Host in Zabbix
   ```

## Zabbix Configuration

### Option 1: Import Template (Recommended)
1. Log in to Zabbix.
2. Go to **Data collection** -> **Templates**.
3. Click **Import** in the top right.
4. Select the `zabbix_vspc_template.xml` file provided in this repo.
5. Link this template to the Host you specified in `ZABBIX_HOST_NAME` (e.g., `VSPC-Monitor`).

### Option 2: Manual Setup
If you prefer to set it up manually:
1. **Create a Host** (e.g., `VSPC-Monitor`).
2. **Create a Discovery Rule:**
   - **Name:** VSPC Job Discovery
   - **Type:** Zabbix trapper
   - **Key:** `vspc.jobs.discovery`
3. **Create Item Prototypes** inside the Discovery Rule:
   - **Name:** Job Status: {#JOBNAME}
   - **Type:** Zabbix trapper
   - **Key:** `vspc.job.status[{#JOBNAME}]`
   - **Type of information:** Text (or Character)
4. **Create Regular Items** (Trapper) for counters:
   - `vspc.stats.success_count` (Numeric unsigned)
   - `vspc.stats.failed_count` (Numeric unsigned)
   - `vspc.stats.warning_count` (Numeric unsigned)
   - `vspc.stats.total_count` (Numeric unsigned)

## Automation (Cron)

To fetch data periodically (e.g., every 15 minutes), set up a cron job on the machine running the script.

1. Open crontab:
   ```bash
   crontab -e
   ```

2. Add the following line (adjust paths as needed):
   ```bash
   */15 * * * * /path/to/venv/bin/python /path/to/vspc_zabbix.py >> /var/log/vspc_zabbix.log 2>&1
   ```

### Troubleshooting
- **No data in Zabbix?**
  - Check `ZABBIX_HOST_NAME` matches exactly the Host name in Zabbix.
  - Ensure the IP running the script is allowed in Zabbix Server/Proxy config (`AllowedHosts`).
  - Run the script manually to see any errors: `python vspc_zabbix.py`

- **SSL Warnings?**
  - The script suppresses InsecureRequestWarning by default.
