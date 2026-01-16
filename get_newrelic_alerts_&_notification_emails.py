import csv
import os
import sys
import time
from typing import Dict, List, Set
import requests

ACCOUNT_ID = 0 # ACCOUNT ID HERE
OUT_CSV = "policies_email_destinations.csv"

API_KEY = "NEWRELIC API KEY HERE"
if not API_KEY:
    print("ERROR: Please export NEW_RELIC_API_KEY in your environment.", file=sys.stderr)
    sys.exit(1)

# Endpoint selection
endpoint = "https://api.newrelic.com/graphql"
if os.getenv("NEW_RELIC_REGION", "").strip().upper() == "EU":
    endpoint = "https://api.eu.newrelic.com/graphql"

HEADERS = {
    "Content-Type": "application/json",
    "API-Key": API_KEY,
}

# -----------------------------
# GraphQL query strings
# -----------------------------

POLICIES_QUERY = """
query Policies($accountId: Int!, $cursor: String) {
  actor {
    account(id: $accountId) {
      alerts {
        policiesSearch(cursor: $cursor) {
          policies {
            id
            name
            incidentPreference
          }
          nextCursor
          totalCount
        }
      }
    }
  }
}
"""

WORKFLOWS_QUERY = """
query Workflows($accountId: Int!, $cursor: String) {
  actor {
    account(id: $accountId) {
      aiWorkflows {
        workflows(filters: {}, cursor: $cursor) {
          entities {
            id
            name
            issuesFilter {
              name
              type
              predicates {
                attribute
                operator
                values
              }
            }
            destinationConfigurations {
              channelId
              name
              type
              notificationTriggers
            }
          }
          nextCursor
          totalCount
        }
      }
    }
  }
}
"""

CHANNELS_EMAIL_QUERY = """
query EmailChannels($accountId: Int!, $cursor: String) {
  actor {
    account(id: $accountId) {
      aiNotifications {
        channels(filters: { type: EMAIL }, cursor: $cursor) {
          entities {
            id
            name
            destinationId
            properties {
              key
              value
            }
          }
          nextCursor
          totalCount
          error { details }
        }
      }
    }
  }
}
"""

DESTINATIONS_EMAIL_QUERY = """
query EmailDestinations($accountId: Int!, $cursor: String) {
  actor {
    account(id: $accountId) {
      aiNotifications {
        destinations(filters: { type: EMAIL }, cursor: $cursor) {
          entities {
            id
            name
            type
            properties {
              key
              value
              displayValue
              label
            }
          }
          nextCursor
          totalCount
          error { details }
        }
      }
    }
  }
}
"""

# -----------------------------
# Helpers
# -----------------------------

def gql_paginated(query: str, variables: Dict, root_path: List[str], session: requests.Session) -> List[Dict]:
    """
    Executes a paginated NerdGraph query until nextCursor is empty.
    root_path: path from response root to the container that has { entities|policies|... , nextCursor }
    Returns a list of collected 'entities' or 'policies' depending on the query shape.
    """
    items: List[Dict] = []
    cursor = None
    while True:
        variables["cursor"] = cursor
        resp = session.post(endpoint, headers=HEADERS, json={"query": query, "variables": variables}, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        if "errors" in data and data["errors"]:
            raise RuntimeError(f"NerdGraph errors: {data['errors']}")

        node = data.get("data", {})
        for key in root_path:
            node = node.get(key, {})

        batch = node.get("entities")
        if batch is None:
            batch = node.get("policies")

        if not isinstance(batch, list):
            batch = []

        items.extend(batch)
        cursor = node.get("nextCursor")
        if not cursor:
            break

        time.sleep(0.1)

    return items


def extract_policy_ids_from_workflow(workflow: Dict) -> Set[str]:
    """
    From workflow.issuesFilter.predicates, extract values where attribute == "labels.policyIds".
    Values can be strings or numbers. We normalize to string.
    """
    policy_ids: Set[str] = set()
    issues_filter = workflow.get("issuesFilter") or {}
    for pred in issues_filter.get("predicates") or []:
        if (pred.get("attribute") or "").strip() == "labels.policyIds":
            for v in pred.get("values") or []:
                policy_ids.add(str(v).strip())
    return policy_ids


def destination_email_from_properties(properties: List[Dict]) -> List[str]:
    """Return all email values from destination properties where key == 'email'."""
    emails: List[str] = []
    for p in properties or []:
        if (p.get("key") or "").lower() == "email":
            val = (p.get("value") or "").strip()
            if val:
                emails.append(val)
    return emails


def main():
    session = requests.Session()

    policies = gql_paginated(
        POLICIES_QUERY,
        {"accountId": ACCOUNT_ID},
        root_path=["actor", "account", "alerts", "policiesSearch"],
        session=session,
    )

    policy_map: Dict[str, str] = {str(p["id"]): p["name"] for p in policies}

    workflows = gql_paginated(
        WORKFLOWS_QUERY,
        {"accountId": ACCOUNT_ID},
        root_path=["actor", "account", "aiWorkflows", "workflows"],
        session=session,
    )

    policy_to_channel_ids: Dict[str, Set[str]] = {}
    for wf in workflows:
        channel_ids = [dc.get("channelId") for dc in (wf.get("destinationConfigurations") or []) if dc.get("channelId")]
        if not channel_ids:
            continue
        wf_policy_ids = extract_policy_ids_from_workflow(wf)
        for pid in wf_policy_ids:
            policy_to_channel_ids.setdefault(pid, set()).update(channel_ids)

    channels = gql_paginated(
        CHANNELS_EMAIL_QUERY,
        {"accountId": ACCOUNT_ID},
        root_path=["actor", "account", "aiNotifications", "channels"],
        session=session,
    )

    channel_to_destination: Dict[str, str] = {}
    for ch in channels:
        cid = ch.get("id")
        did = ch.get("destinationId")
        if cid and did:
            channel_to_destination[cid] = did

    destinations = gql_paginated(
        DESTINATIONS_EMAIL_QUERY,
        {"accountId": ACCOUNT_ID},
        root_path=["actor", "account", "aiNotifications", "destinations"],
        session=session,
    )
    destination_to_emails: Dict[str, List[str]] = {}
    for dest in destinations:
        did = dest.get("id")
        emails = destination_email_from_properties(dest.get("properties") or [])
        if did and emails:
            destination_to_emails[did] = emails

    rows: List[List[str]] = []
    for pid, pname in policy_map.items():
        chan_ids = policy_to_channel_ids.get(pid, set())
        email_set: Set[str] = set()
        for cid in chan_ids:
            did = channel_to_destination.get(cid)
            if not did:
                continue
            for e in destination_to_emails.get(did, []):
                email_set.add(e)
        rows.append([pname, ", ".join(sorted(email_set))])

    rows.sort(key=lambda r: r[0].lower())

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Alert Policy", "Email Destinations"])
        w.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUT_CSV}")

if __name__ == "__main__":
    main()