#!/usr/bin/env python3
"""
Trello Card Mirroring Script

Mirrors cards from Proposals and Papers boards to Master board based on:
1. Cards in "Priority IV" list, OR
2. Cards with "In-Progress" checklist ≥ 75% complete
3. Cards must NOT have "Completed" label (case-insensitive)

Runs every Monday at 8 AM Eastern via GitHub Actions.
"""

import os
import requests
from datetime import datetime
from typing import List, Dict, Optional

# Load environment variables
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")

if not TRELLO_API_KEY or not TRELLO_TOKEN:
    raise ValueError("Missing TRELLO_API_KEY or TRELLO_TOKEN environment variables")

# Board and List IDs (use the ones from mirror_priority_cards.py as they seem more recent)
PROPOSALS_BOARD_ID = "6862042608fdc9ecc66f793b"
PAPERS_BOARD_ID = "6866dd4609df4573a20ba546"
MASTER_BOARD_ID = "685c44d7f65b2a102409f67b"
MASTER_PROPOSALS_LIST_ID = "685d5ad92a6725cdeb415f91"
MASTER_PAPERS_LIST_ID = "685d5ad7a89f68ae6d215449"

# Constants
PRIORITY_LIST_NAME = "Priority IV"
PROGRESS_CHECKLIST_NAME = "In-Progress"
COMPLETED_LABEL_NAME = "Completed"
COMPLETION_THRESHOLD = 0.75

HEADERS = {"Accept": "application/json"}

class TrelloAPI:
    """Wrapper for Trello API calls"""
    
    def __init__(self, api_key: str, token: str):
        self.api_key = api_key
        self.token = token
        self.base_params = {"key": api_key, "token": token}
    
    def get(self, endpoint: str, params: Dict = None) -> requests.Response:
        """Make GET request to Trello API"""
        url = f"https://api.trello.com/1/{endpoint}"
        all_params = {**self.base_params, **(params or {})}
        return requests.get(url, params=all_params, headers=HEADERS)
    
    def post(self, endpoint: str, data: Dict = None) -> requests.Response:
        """Make POST request to Trello API"""
        url = f"https://api.trello.com/1/{endpoint}"
        all_data = {**self.base_params, **(data or {})}
        return requests.post(url, data=all_data, headers=HEADERS)
    
    def delete(self, endpoint: str) -> requests.Response:
        """Make DELETE request to Trello API"""
        url = f"https://api.trello.com/1/{endpoint}"
        return requests.delete(url, params=self.base_params, headers=HEADERS)

def get_all_cards_from_board(api: TrelloAPI, board_id: str) -> List[Dict]:
    """Get all open cards from a board with full details"""
    response = api.get(f"boards/{board_id}/cards", {
        "cards": "open",
        "attachments": "true",
        "checklists": "all",
        "members": "true"
    })
    
    if response.status_code != 200:
        print(f"❌ Failed to fetch cards from board {board_id}: {response.text}")
        return []
    
    return response.json()

def get_list_name(api: TrelloAPI, list_id: str) -> str:
    """Get the name of a list"""
    response = api.get(f"lists/{list_id}")
    if response.status_code != 200:
        print(f"❌ Failed to fetch list {list_id}: {response.text}")
        return ""
    return response.json().get("name", "")

def get_board_labels(api: TrelloAPI, board_id: str) -> Dict[str, str]:
    """Get all labels for a board, return dict of {label_id: label_name}"""
    response = api.get(f"boards/{board_id}/labels")
    if response.status_code != 200:
        print(f"❌ Failed to fetch labels for board {board_id}: {response.text}")
        return {}
    
    return {label["id"]: label["name"] for label in response.json()}

def has_completed_label(card: Dict, board_labels: Dict[str, str]) -> bool:
    """Check if card has a 'Completed' label (case-insensitive)"""
    for label_id in card.get("idLabels", []):
        label_name = board_labels.get(label_id, "")
        if label_name.lower() == COMPLETED_LABEL_NAME.lower():
            return True
    return False

def get_checklist_progress(card: Dict, checklist_name: str) -> float:
    """Get completion percentage for a specific checklist"""
    for checklist in card.get("checklists", []):
        if checklist["name"].lower() == checklist_name.lower():
            total_items = len(checklist["checkItems"])
            if total_items == 0:
                return 0.0
            completed_items = sum(1 for item in checklist["checkItems"] if item["state"] == "complete")
            return completed_items / total_items
    return 0.0

def should_mirror_card(api: TrelloAPI, card: Dict, board_labels: Dict[str, str]) -> bool:
    """Determine if a card should be mirrored based on criteria"""
    # Skip if card has "Completed" label
    if has_completed_label(card, board_labels):
        print(f"🚫 Skipping '{card['name']}' - has Completed label")
        return False
    
    # Check if card is in Priority IV list
    list_name = get_list_name(api, card["idList"])
    if list_name.lower() == PRIORITY_LIST_NAME.lower():
        print(f"✅ '{card['name']}' - in Priority IV list")
        return True
    
    # Check if card has In-Progress checklist ≥ 75% complete
    progress = get_checklist_progress(card, PROGRESS_CHECKLIST_NAME)
    if progress >= COMPLETION_THRESHOLD:
        print(f"✅ '{card['name']}' - In-Progress checklist {progress:.1%} complete")
        return True
    
    if progress > 0:
        print(f"⏳ Skipping '{card['name']}' - In-Progress checklist only {progress:.1%} complete")
    else:
        print(f"⏳ Skipping '{card['name']}' - no qualifying criteria met")
    
    return False

def clear_list(api: TrelloAPI, list_id: str, list_name: str) -> None:
    """Clear all cards from a list"""
    response = api.get(f"lists/{list_id}/cards")
    if response.status_code != 200:
        print(f"❌ Failed to fetch cards from {list_name}: {response.text}")
        return
    
    cards = response.json()
    for card in cards:
        delete_response = api.delete(f"cards/{card['id']}")
        if delete_response.status_code != 200:
            print(f"❌ Failed to delete card '{card['name']}': {delete_response.text}")
    
    print(f"🧹 Cleared {len(cards)} cards from {list_name} list")

def mirror_card(api: TrelloAPI, card: Dict, target_list_id: str, source_board_name: str) -> bool:
    """Mirror a card to the target list with all its properties"""
    # Create the card
    card_data = {
        "idList": target_list_id,
        "name": card["name"],
        "desc": card["desc"] + f"\n\n🤖 Mirrored from {source_board_name} on {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "due": card.get("due", ""),
        "pos": "bottom"
    }
    
    response = api.post("cards", card_data)
    if response.status_code != 200:
        print(f"❌ Failed to create card '{card['name']}': {response.text}")
        return False
    
    new_card = response.json()
    new_card_id = new_card["id"]
    
    # Add members
    for member_id in card.get("idMembers", []):
        api.post(f"cards/{new_card_id}/idMembers", {"value": member_id})
    
    # Add labels
    for label_id in card.get("idLabels", []):
        api.post(f"cards/{new_card_id}/idLabels", {"value": label_id})
    
    # Add attachments
    for attachment in card.get("attachments", []):
        if attachment.get("url"):
            api.post(f"cards/{new_card_id}/attachments", {"url": attachment["url"]})
    
    # Mirror checklists
    for checklist in card.get("checklists", []):
        checklist_response = api.post(f"cards/{new_card_id}/checklists", {"name": checklist["name"]})
        if checklist_response.status_code == 200:
            new_checklist_id = checklist_response.json()["id"]
            
            # Add checklist items
            for item in checklist.get("checkItems", []):
                item_data = {
                    "name": item["name"],
                    "checked": str(item["state"] == "complete").lower()
                }
                api.post(f"checklists/{new_checklist_id}/checkItems", item_data)
    
    # Add comment
    api.post(f"cards/{new_card_id}/actions/comments", {
        "text": f"🤖 Mirrored from {source_board_name} board"
    })
    
    print(f"✅ Successfully mirrored: '{card['name']}'")
    return True

def process_board(api: TrelloAPI, board_id: str, board_name: str, master_list_id: str) -> int:
    """Process a board and mirror qualifying cards"""
    print(f"\n📋 Processing {board_name} board...")
    
    # Get all cards and board labels
    cards = get_all_cards_from_board(api, board_id)
    board_labels = get_board_labels(api, board_id)
    
    if not cards:
        print(f"⚠️  No cards found on {board_name} board")
        return 0
    
    print(f"📊 Found {len(cards)} cards on {board_name} board")
    
    # Process each card
    mirrored_count = 0
    for card in cards:
        if should_mirror_card(api, card, board_labels):
            if mirror_card(api, card, master_list_id, board_name):
                mirrored_count += 1
    
    print(f"📤 Mirrored {mirrored_count} cards from {board_name} board")
    return mirrored_count

def main():
    """Main execution function"""
    print("🚀 Starting Trello Card Mirror Script")
    print(f"⏰ Started at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    # Initialize API
    api = TrelloAPI(TRELLO_API_KEY, TRELLO_TOKEN)
    
    # Clear master board lists
    print("\n🧹 Clearing Master Board lists...")
    clear_list(api, MASTER_PROPOSALS_LIST_ID, "Master Proposals")
    clear_list(api, MASTER_PAPERS_LIST_ID, "Master Papers")
    
    # Process boards
    total_mirrored = 0
    total_mirrored += process_board(api, PROPOSALS_BOARD_ID, "Proposals", MASTER_PROPOSALS_LIST_ID)
    total_mirrored += process_board(api, PAPERS_BOARD_ID, "Papers", MASTER_PAPERS_LIST_ID)
    
    print(f"\n🎉 Script completed successfully!")
    print(f"📊 Total cards mirrored: {total_mirrored}")
    print(f"⏰ Finished at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")

if __name__ == "__main__":
    main()
