import re
from typing import List, Dict


def parse_funding_text(text: str) -> Dict[str, List[Dict]]:
    """
    Parses structured funding message text into:
    - List title
    - Card titles + descriptions + attachment links
    """
    lines = text.strip().split('\n')
    lines = [line.rstrip() for line in lines if line.strip()]

    list_title = lines[0].strip()
    entries = []

    current_card = None

    for line in lines[1:]:
        # New card title (not indented)
        if not line.startswith(" "):
            if current_card:
                entries.append(current_card)
            current_card = {
                "title": line.strip(),
                "description_lines": [],
                "attachments": []
            }
        elif current_card:
            # Indented line — part of description or link
            stripped = line.strip()

            # Extract all .gov links and convert to https URLs
            gov_domains = re.findall(r'([\w.-]+\.gov)', stripped)
            for domain in gov_domains:
                if domain not in current_card["attachments"]:
                    current_card["attachments"].append(f"https://{domain}")

            current_card["description_lines"].append(stripped)

    if current_card:
        entries.append(current_card)

    # Final formatting
    for card in entries:
        card["description"] = "\n".join(card["description_lines"])
        del card["description_lines"]

    return {
        "list_title": list_title,
        "cards": entries
    }
