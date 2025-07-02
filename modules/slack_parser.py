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
    
    if not lines:
        return {"list_title": "", "cards": []}

    list_title = lines[0].strip()
    entries = []
    current_card = None

    for line in lines[1:]:
        # Check if this is a numbered list item (new card)
        if re.match(r'^\d+\.\s+', line):
            # Save previous card if exists
            if current_card:
                entries.append(current_card)
            
            # Start new card
            card_title = re.sub(r'^\d+\.\s+', '', line).strip()
            current_card = {
                "title": card_title,
                "description_lines": [],
                "attachments": []
            }
        elif current_card and line.startswith('   '):
            # This is a sub-item (bullet point under a numbered item)
            stripped = line.strip()
            
            # Extract URLs from the line
            urls = re.findall(r'(https?://[^\s]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?)', stripped, re.IGNORECASE)
            for url in urls:
                if not url.startswith("http"):
                    url = f"https://{url}"
                if url not in current_card["attachments"]:
                    current_card["attachments"].append(url)
            
            current_card["description_lines"].append(stripped)

    # Don't forget the last card
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