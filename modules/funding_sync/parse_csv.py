import pandas as pd

def load_funding_csv(path):
    df = pd.read_csv(path)
    entries = []
    for _, row in df.iterrows():
        entries.append({
            "title": str(row.get("OPPORTUNITY TITLE", "")).strip(),
            "description": str(row.get("FUNDING DESCRIPTION", "")).strip(),
            "close_date": str(row.get("CLOSE DATE", "")).strip(),
            "link": str(row.get("OPPORTUNITY NUMBER", "")).split('"')[1]  # Extract link from HYPERLINK() if needed
        })
    return entries
