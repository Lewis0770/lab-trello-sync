import os
import requests
from typing import List, Dict
import time

# --- Environment variables / tokens
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
TRELLO_BOARD_ID = os.getenv("TRELLO_BOARD_ID", "68642fae07900e6d2d7d79bc")

if not TRELLO_API_KEY or not TRELLO_TOKEN:
    raise EnvironmentError("Missing TRELLO_API_KEY or TRELLO_TOKEN in environment variables.")

def get_or_create_list(list_name: str) -> str:
    """Get existing list or create new one on Trello board"""
    print(f"🔍 Looking for list: '{list_name}'")
    
    # Get all lists on the board
    url = f"https://api.trello.com/1/boards/{TRELLO_BOARD_ID}/lists"
    params = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}
    
    try:
        res = requests.get(url, params=params)
        res.raise_for_status()
        lists = res.json()
        
        # Check if list already exists (case-insensitive)
        for lst in lists:
            if lst["name"].strip().lower() == list_name.strip().lower():
                print(f"✅ Found existing list: '{lst['name']}'")
                return lst["id"]

        # List not found, create new one
        print(f"➕ Creating new list: '{list_name}'")
        url = "https://api.trello.com/1/lists"
        data = {
            "key": TRELLO_API_KEY,
            "token": TRELLO_TOKEN,
            "name": list_name,
            "idBoard": TRELLO_BOARD_ID,
            "pos": "bottom"
        }
        res = requests.post(url, data=data)
        res.raise_for_status()
        new_list = res.json()
        print(f"✅ Created list: '{new_list['name']}'")
        return new_list["id"]
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error with Trello API: {e}")
        raise

def create_card(list_id: str, name: str, desc: str, attachments: List[str]) -> Dict:
    """Create a new card in the specified Trello list"""
    print(f"📝 Creating card: '{name}'")
    
    # Create the card
    url = "https://api.trello.com/1/cards"
    data = {
        "key": TRELLO_API_KEY,
        "token": TRELLO_TOKEN,
        "idList": list_id,
        "name": name,
        "desc": desc
    }
    
    try:
        res = requests.post(url, data=data)
        res.raise_for_status()
        card = res.json()
        print(f"✅ Created card: '{card['name']}'")

        # Add attachments if any
        if attachments:
            print(f"📎 Adding {len(attachments)} attachments...")
            for i, link in enumerate(attachments):
                try:
                    attach_url = f"https://api.trello.com/1/cards/{card['id']}/attachments"
                    attach_data = {
                        "key": TRELLO_API_KEY,
                        "token": TRELLO_TOKEN,
                        "url": link
                    }
                    attach_res = requests.post(attach_url, data=attach_data)
                    attach_res.raise_for_status()
                    print(f"   ✅ Added attachment {i+1}: {link}")
                    
                    # Small delay to avoid rate limiting
                    time.sleep(0.1)
                    
                except requests.exceptions.RequestException as e:
                    print(f"   ⚠️ Failed to add attachment {link}: {e}")

        return card
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error creating card: {e}")
        raise

def test_trello_connection():
    """Test if Trello API credentials are working"""
    print("🔧 Testing Trello connection...")
    
    url = f"https://api.trello.com/1/boards/{TRELLO_BOARD_ID}"
    params = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}
    
    try:
        res = requests.get(url, params=params)
        res.raise_for_status()
        board_info = res.json()
        print(f"✅ Connected to Trello board: '{board_info['name']}'")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to connect to Trello: {e}")
        return False

if __name__ == "__main__":
    # Test the connection
    if test_trello_connection():
        print("✅ Trello connection test passed!")
    else:
        print("❌ Trello connection test failed!")