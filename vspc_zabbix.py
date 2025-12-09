import requests
import urllib3
import json
import time
from pyzabbix import ZabbixMetric, ZabbixSender

# Disable SSL warnings (VSPC typically uses self-signed certs)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- VSPC CONFIGURATION ---
# Replace these values with your actual VSPC details
BASE_URL = "https://your-vspc-address.com/api/v3"
USERNAME = "your-vspc-username"
PASSWORD = "your-vspc-password"

# --- ZABBIX CONFIGURATION ---
ENABLE_ZABBIX = True
ZABBIX_SERVER_IP = "127.0.0.1"  # IP of your Zabbix Server or Proxy
ZABBIX_HOST_NAME = "VSPC-Monitor"  # Hostname as configured in Zabbix

# --- ZABBIX LLD & ITEMS KEYS ---
# Do not change these unless you edit the Zabbix Template accordingly
KEY_DISCOVERY = "vspc.jobs.discovery"
KEY_ITEM_PROTO = "vspc.job.status"

# --- STATS COUNTER KEYS ---
KEY_COUNT_SUCCESS = "vspc.stats.success_count"
KEY_COUNT_FAILED  = "vspc.stats.failed_count"
KEY_COUNT_WARNING = "vspc.stats.warning_count"
KEY_COUNT_TOTAL   = "vspc.stats.total_count"

def get_access_token():
    """Authenticates with VSPC and returns the bearer token."""
    token_url = f"{BASE_URL}/token"
    payload = {'grant_type': 'password', 'username': USERNAME, 'password': PASSWORD}
    headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'}
    try:
        response = requests.post(token_url, data=payload, headers=headers, verify=False)
        if response.status_code == 200:
            return response.json().get('access_token')
        else:
            print(f"Login Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Login Error: {e}")
    return None

def fetch_data(token, endpoint_suffix, label):
    """
    Fetches all paginated data from a specific VSPC endpoint.
    """
    endpoint = f"{BASE_URL}{endpoint_suffix}"
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json'
    }
    
    all_items = []
    limit = 100
    offset = 0
    
    print(f"--- Fetching {label} ---")
    
    while True:
        params = {'limit': limit, 'offset': offset}
        try:
            response = requests.get(endpoint, headers=headers, params=params, verify=False)
            
            if response.status_code == 404:
                print(f"   -> Endpoint not found or empty.")
                break

            response.raise_for_status()
            data = response.json()
            
            if 'data' in data and isinstance(data['data'], list):
                items = data['data']
                if not items:
                    break
                
                all_items.extend(items)
                
                if len(items) < limit:
                    break
                offset += limit
            else:
                break
        except Exception as e:
            print(f"Error downloading {label}: {e}")
            break
            
    return all_items

def send_to_zabbix(metrics):
    """Sends a list of ZabbixMetric objects to Zabbix Trapper."""
    if not metrics: return
    sender = ZabbixSender(zabbix_server=ZABBIX_SERVER_IP)
    try:
        res = sender.send(metrics)
        print(f"ZABBIX RESPONSE: {res}")
    except Exception as e:
        print(f"Zabbix Send Error: {e}")

def main():
    token = get_access_token()
    
    if not token:
        print("Could not obtain access token. Exiting.")
        return

    if not ENABLE_ZABBIX:
        print("Zabbix integration is disabled in config.")
        return

    print("\n1. Starting data collection from VSPC...")
    
    # 1. Fetch VM Jobs (VBR)
    vm_jobs = fetch_data(token, "/infrastructure/backupServers/jobs", "VM Jobs")
    
    # 2. Fetch Agent Jobs (VBR managed)
    agent_vbr = fetch_data(token, "/infrastructure/backupServers/jobs/agentJobs", "Agent Jobs (VBR)")
    
    # 3. Fetch Agent Jobs (Standalone / VSPC Direct)
    agent_vspc = fetch_data(token, "/infrastructure/backupAgents/jobs", "Agent Jobs (Standalone)")
    
    # Combine all jobs
    all_jobs_data = vm_jobs + agent_vbr + agent_vspc
    
    if all_jobs_data:
        discovery_payload = []
        status_metrics = []
        
        # --- INITIALIZE COUNTERS ---
        count_success = 0
        count_failed = 0
        count_warning = 0
        count_total = 0

        print(f"\n--- PROCESSING JOBS (Total found: {len(all_jobs_data)}) ---")
        print(f"{'JOB NAME':<40} | {'STATUS':<10}")
        print("-" * 80)

        for job in all_jobs_data:
            name = job.get('name', 'Unknown')
            
            # Filter Disabled Jobs
            # Note: If 'isEnabled' is missing, assume True (common for some agent types)
            is_enabled = job.get('isEnabled', True)
            if is_enabled is False:
                continue

            count_total += 1
            
            # Normalize STATUS: VSPC uses 'status' or 'lastResult' depending on job type
            raw_status = job.get('status') or job.get('lastResult') or 'Unknown'
            
            # Map None to 'Unknown'
            value_to_send = raw_status if raw_status else 'Unknown'
            
            # Handle "Never Run" case
            if value_to_send == 'Unknown':
                    value_to_send = "NotRun"

            # Prepare LLD payload
            discovery_payload.append({"{#JOBNAME}": name})
            
            # --- UPDATE COUNTERS ---
            if value_to_send == "Success":
                count_success += 1
            elif value_to_send == "Failed":
                count_failed += 1
            elif value_to_send == "Warning":
                count_warning += 1
            
            # Create Zabbix Metric for individual Job Status
            key = f"{KEY_ITEM_PROTO}[{name}]"
            status_metrics.append(ZabbixMetric(ZABBIX_HOST_NAME, key, value_to_send))
            
            # Print to console (truncated)
            p_name = (name[:37] + '..') if len(name) > 37 else name
            print(f"{p_name:<40} | {value_to_send}")

        print("-" * 80)
        print(f"STATS: Tot:{count_total} | OK:{count_success} | Fail:{count_failed} | Warn:{count_warning}")

        # Add Global Metrics
        status_metrics.append(ZabbixMetric(ZABBIX_HOST_NAME, KEY_COUNT_SUCCESS, count_success))
        status_metrics.append(ZabbixMetric(ZABBIX_HOST_NAME, KEY_COUNT_FAILED, count_failed))
        status_metrics.append(ZabbixMetric(ZABBIX_HOST_NAME, KEY_COUNT_WARNING, count_warning))
        status_metrics.append(ZabbixMetric(ZABBIX_HOST_NAME, KEY_COUNT_TOTAL, count_total))

        if discovery_payload:
            print(f"\n[1] Sending LLD Discovery ({len(discovery_payload)} items)...")
            disc_metric = [ZabbixMetric(ZABBIX_HOST_NAME, KEY_DISCOVERY, json.dumps({"data": discovery_payload}))]
            send_to_zabbix(disc_metric)
            
            print("Waiting 5 seconds for Zabbix server processing...")
            time.sleep(5)

            print(f"[2] Sending Item Values & Counters ({len(status_metrics)} items)...")
            send_to_zabbix(status_metrics)
        else:
            print("No active jobs found to report.")
    else:
        print("No data retrieved from VSPC APIs.")

if __name__ == "__main__":
    main()
