from actions.slack import send_message
from actions.virustotal import lookup_ip
from actions.webhook import get_payload


def format_message(result: dict) -> str:
    return (
        f"*IP Enrichment Result*\n"
        f"*IP:* {result['ip']}\n"
        f"*Verdict:* {result['verdict']}\n"
        f"*Detection Stats:* malicious={result['malicious']}, suspicious={result['suspicious']}, harmless={result['harmless']}\n"
        f"*Country:* {result['country']}\n"
        f"*ISP:* {result['isp']}\n"
        f"*VirusTotal Report:* {result['link']}"
    )


def main() -> None:
    payload = get_payload()
    result = lookup_ip(payload["ip"])
    send_message(format_message(result))


if __name__ == "__main__":
    main()
