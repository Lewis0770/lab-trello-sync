import json
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
    text = (entry["title"] + " " + entry["description"]).lower()
    return any(k.lower() in text for k in keywords)
