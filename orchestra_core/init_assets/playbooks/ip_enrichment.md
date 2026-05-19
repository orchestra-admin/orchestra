# Playbook: IP Enrichment with Slack Notification

## Description
This script receives an IP address via webhook payload, enriches it by querying VirusTotal, and sends the result to a Slack channel.

## Inputs
- Webhook JSON payload on stdin: `{"event_type": "ip_enrichment", "ip": "1.1.1.1"}`

## Invocation
This playbook is triggered by a webhook `POST` to `/webhook`.

## Steps
1. Read the IP address from the webhook payload using `actions.webhook.get_payload`.
2. Query VirusTotal using `actions.virustotal.lookup_ip`.
3. Format the enrichment result into a human-readable message string.
4. Send the formatted message to Slack using `actions.slack.send_message`.

## Output
- A Slack message containing the IP enrichment verdict, detection stats, country, ISP, and a link to the full VirusTotal report.
