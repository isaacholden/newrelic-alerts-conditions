import requests
import csv

API_KEY = "YOUR-API-KEY-HERE"
HEADERS = {
    "Api-Key": API_KEY,
    "Content-Type": "application/json"
}

# Base URLs
POLICIES_URL = "https://api.newrelic.com/v2/alerts_policies.json"
CONDITIONS_URL = "https://api.newrelic.com/v2/alerts_conditions.json"
CONDITIONS_NRQL_URL = "https://api.newrelic.com/v2/alerts_nrql_conditions.json"
CONDITIONS_ENTITY_URL = "https://api.newrelic.com/v2/alerts_infrastructure_conditions.json"
CONDITIONS_EXTERNAL_SERVICES_URL = "https://api.newrelic.com/v2/alerts_external_service_conditions.json"
CONDITIONS_SYNTHETICS_URL = "https://api.newrelic.com/v2/alerts_synthetics_conditions.json"
ALERT_CHANNELS_URL = "https://api.newrelic.com/v2/alerts_channels.json"

# Get all alert policies
def get_policies():
    policies = []
    page = 1
    while True:
        response = requests.get(POLICIES_URL, headers=HEADERS, params={"page": page})
        data = response.json()
        if "policies" not in data or not data["policies"]:
            break
        policies.extend(data["policies"])
        page += 1
    return policies
    
def get_alerts_channels():
    alerts_channels = []
    page = 1
    while True:
        response = requests.get(ALERT_CHANNELS_URL, headers=HEADERS, params={"page": page})
        data = response.json()
        if len(data["channels"]) == 0:
            break
        alerts_channels.extend(data["channels"])
        page += 1
    return alerts_channels

def get_conditions(policy_id):
    response = requests.get(CONDITIONS_URL, headers=HEADERS, params={"policy_id": policy_id})
    return response.json().get("conditions", [])
    
def get_nrql_conditions(policy_id):
    response = requests.get(CONDITIONS_NRQL_URL, headers=HEADERS, params={"policy_id": policy_id})
    return response.json().get("nrql_conditions", [])
    
def get_external_service_conditions(policy_id):
    response = requests.get(CONDITIONS_EXTERNAL_SERVICES_URL, headers=HEADERS, params={"policy_id": policy_id})
    return response.json().get("nrql_conditions", [])
    
def get_synthetics_conditions(policy_id):
    response = requests.get(CONDITIONS_SYNTHETICS_URL, headers=HEADERS, params={"policy_id": policy_id})
    return response.json().get("nrql_conditions", [])

# Main logic
def export_conditions_to_csv():
    policies = get_policies()
    alerts_channels = get_alerts_channels()
    
    with open("newrelic_alert_conditions.csv", "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Policy Name", "Condition Name", "Email", "Type", "Condition Type", "Enabled", "Threshold", "Duration", "Entities"])
        for policy in policies:       
            matching_channels = []            
            for item in alerts_channels:
                if item["type"] != "email" or len(item["links"]["policy_ids"]) == 0 or policy["id"] not in item["links"]["policy_ids"]:
                    continue
                matching_channels.append(item["name"])
            conditions = get_conditions(policy["id"])
            nrql_conditions = get_nrql_conditions(policy["id"])
            external_conditions = get_external_service_conditions(policy["id"])
            synthetic_conditions = get_synthetics_conditions(policy["id"])
            if len(matching_channels) == 0:
                matching_channels.append("N/A")
            for cond in conditions:
                for matching_channel in matching_channels:
                    writer.writerow([
                        policy["name"],
                        cond.get("name"),
                        matching_channel,
                        cond.get("type"),
                        "Condition",
                        cond.get("enabled"),
                        cond.get("terms", [{}])[0].get("threshold"),
                        cond.get("terms", [{}])[0].get("duration"),
                        ", ".join(cond.get("entities", []))
                    ])
            for cond in nrql_conditions:
                for matching_channel in matching_channels:
                    writer.writerow([
                        policy["name"],
                        cond.get("name"),
                        matching_channel,
                        cond.get("type"),
                        "NRQL",
                        cond.get("enabled"),
                        cond.get("terms", [{}])[0].get("threshold"),
                        cond.get("terms", [{}])[0].get("duration"),
                        cond.get("nrql", {}).get("query")
                        ])
            for cond in external_conditions:
                for matching_channel in matching_channels:
                    writer.writerow([
                        policy["name"],
                        cond.get("name"),
                        matching_channel,
                        cond.get("type"),
                        "External Service",
                        cond.get("enabled"),
                        cond.get("terms", [{}])[0].get("threshold"),
                        cond.get("terms", [{}])[0].get("duration"),
                        cond.get("nrql", {}).get("query")
                        ])
            for cond in synthetic_conditions:
                for matching_channel in matching_channels:
                    writer.writerow([
                        policy["name"],
                        cond.get("name"),
                        matching_channel,
                        cond.get("type"),
                        "Synthetic",
                        cond.get("enabled"),
                        cond.get("terms", [{}])[0].get("threshold"),
                        cond.get("terms", [{}])[0].get("duration"),
                        cond.get("nrql", {}).get("query")
                        ]) 
    print("Export complete: newrelic_alert_conditions.csv")
    

# Run the script
export_conditions_to_csv()