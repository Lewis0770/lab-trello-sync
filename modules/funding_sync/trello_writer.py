import os
import requests
from datetime import datetime

# ENV Vars
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
TRELLO_BOARD_ID = "68642fae07900e6d2d7d79bc"

def get_list_id_by_name(list_name):
    """Find or create a Trello list by name on the board."""
    url = f"https://api.trello.com/1/boards/{TRELLO_BOARD_ID}/lists"
    params = {
        "key": TRELLO_API_KEY,
        "token": TRELLO_TOKEN
    }
    response = requests.get(url, params=params)

    if response.status_code != 200:
        print(f"❌ Failed to fetch Trello lists.")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        return None

    try:
        lists = response.json()
    except Exception as e:
        print("❌ Could not decode JSON from Trello list fetch:")
        print("Raw response:", response.text)
        raise e

    for lst in lists:
        if lst["name"].lower() == list_name.lower():
            return lst["id"]

    # If list doesn't exist, create it
    create_url = "https://api.trello.com/1/lists"
    create_params = {
        "name": list_name,
        "idBoard": TRELLO_BOARD_ID,
        "key": TRELLO_API_KEY,
        "token": TRELLO_TOKEN
    }
    create_resp = requests.post(create_url, params=create_params)

    if create_resp.status_code != 200:
        print(f"❌ Failed to create Trello list: {list_name}")
        print(f"Status Code: {create_resp.status_code}")
        print(f"Response: {create_resp.text}")
        return None

    return create_resp.json()["id"]

def get_existing_card_titles(list_id):
    """Return a set of card titles already on the list."""
    url = f"https://api.trello.com/1/lists/{list_id}/cards"
    params = {
        "key": TRELLO_API_KEY,
        "token": TRELLO_TOKEN,
        "fields": "name"
    }
    response = requests.get(url, params=params)

    if response.status_code != 200:
        print(f"❌ Failed to fetch cards for list {list_id}")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        return set()

    try:
        cards = response.json()
    except Exception as e:
        print("❌ Could not decode JSON from Trello card fetch:")
        print("Raw response:", response.text)
        raise e

    return set(card["name"].strip().lower() for card in cards)

def create_card(entry, list_name):
    """Create a Trello card with a due date if not a duplicate."""
    list_id = get_list_id_by_name(list_name)
    if not list_id:
        print(f"🚫 Skipping card due to list fetch failure: {entry['title']}")
        return

    existing_titles = get_existing_card_titles(list_id)

    title = entry["title"].strip()
    normalized_title = title.lower()

    if normalized_title in existing_titles:
        print(f"⏭️ Skipping duplicate: {title}")
        return None

    description = entry.get("description", "")
    link = entry.get("link", "")
    full_desc = f"{description}\n\nLink: {link}"

    # Parse due date from CLOSE DATE
    try:
        due_date = datetime.strptime(entry["close_date"], "%m/%d/%Y").isoformat()
    except:
        due_date = None

    url = "https://api.trello.com/1/cards"
    params = {
        "key": TRELLO_API_KEY,
        "token": TRELLO_TOKEN,
        "idList": list_id,
        "name": title,
        "desc": full_desc,
        "due": due_date
    }

    response = requests.post(url, params=params)

    if response.status_code == 200:
        print(f"✅ Created card: {title}")
    else:
        print(f"❌ Failed to create card: {title}")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
