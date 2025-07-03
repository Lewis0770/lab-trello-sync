import json
import re
from datetime import datetime

def load_keywords(path):
    with open(path) as f:
        return json.load(f)["lab_keywords"]

def is_future_entry(entry):
    try:
        close_date = datetime.strptime(entry["close_date"], "%m/%d/%Y")
        return close_date >= datetime.today()
    except:
        return False

def contains_keyword(entry, keywords):
    """Check if entry contains any of the lab keywords using whole-word matching."""
    text = (entry["title"] + " " + entry["description"]).lower()
    matched_keywords = []
    
    for keyword in keywords:
        keyword_lower = keyword.lower()
        # Use word boundaries to match whole words only
        pattern = r'\b' + re.escape(keyword_lower) + r'\b'
        if re.search(pattern, text):
            matched_keywords.append(keyword)
    
    if matched_keywords:
        print(f"🎯 Matched keywords for '{entry['title'][:50]}...': {matched_keywords[:3]}")
    
    return len(matched_keywords) > 0