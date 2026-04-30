import json
import urllib.request
import urllib.error
from .integrations.virustotal_integration import get_api_key as _get_api_key

def lookup_ip(ip: str) -> dict:
    """
    Look up an IP address on VirusTotal and return a structured report.

    Args:
        ip: IPv4 or IPv6 address to look up

    Returns:
        {
            "ip": str,
            "verdict": str,           # "MALICIOUS", "SUSPICIOUS", or "CLEAN"
            "malicious": int,         # engines that flagged as malicious
            "suspicious": int,        # engines that flagged as suspicious
            "harmless": int,          # engines that flagged as harmless
            "country": str,           # two-letter country code, e.g. "US"
            "isp": str,               # AS owner / ISP name
            "reputation": int,        # VirusTotal reputation score
            "link": str               # URL to the full VT report
        }

    Verdict logic:
        malicious > 3           → "MALICIOUS"
        malicious 1–3 OR
          suspicious > 5        → "SUSPICIOUS"
        otherwise               → "CLEAN"
    """
    api_key = _get_api_key()
    url = f"https://www.virustotal.com/api/v3/ip_addresses/{ip}"
    req = urllib.request.Request(
        url,
        headers={
            "x-apikey": api_key,
            "accept": "application/json"
        },
        method="GET"
    )
    
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.load(resp).get("data", {})
    except urllib.error.URLError as e:
        raise Exception(f"VT API Error: {e}")
    
    attributes = data.get("attributes", {})
    stats = attributes.get("last_analysis_stats", {})
    
    malicious = stats.get("malicious", 0)
    suspicious = stats.get("suspicious", 0)
    harmless = stats.get("harmless", 0)
    
    if malicious > 3:
        verdict = "MALICIOUS"
    elif malicious >= 1 or suspicious > 5:
        verdict = "SUSPICIOUS"
    else:
        verdict = "CLEAN"
        
    return {
        "ip": ip,
        "verdict": verdict,
        "malicious": malicious,
        "suspicious": suspicious,
        "harmless": harmless,
        "country": attributes.get("country", "Unknown"),
        "isp": attributes.get("as_owner", "Unknown"),
        "reputation": attributes.get("reputation", 0),
        "link": f"https://www.virustotal.com/gui/ip-address/{ip}"
    }
