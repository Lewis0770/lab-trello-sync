#!/usr/bin/env python3
"""
Trello Card Bi-Directional Mirroring Script

Phase 1: Sync changes from Master board back to source boards
Phase 2: Mirror qualifying cards from source boards to Master board

Mirrors cards from Proposals and Papers boards to Master board based on:
1. Cards in "Priority IV" list, OR
2. Cards with "In-Progress" checklist ≥ 75% complete
3. Cards must NOT have "Completed" label (case-insensitive)

Runs every Monday at 8 AM Eastern via GitHub Actions.
"""

import os
import requests
import json
import re
from datetime import datetime
from typing import List, Dict, Optional, Tuple

# Load environment variables
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")

if not TRELLO_API_KEY or not TRELLO_TOKEN:
    raise ValueError("Missing TRELLO_API_KEY or TRELLO_TOKEN environment variables")

# Board and List IDs
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

# Mirror metadata markers
MIRROR_MARKER = "🤖 MIRROR_METADATA:"
MIRROR_COMMENT_MARKER = "[Bot] Mirrored from"

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
    
    def put(self, endpoint: str, data: Dict = None) -> requests.Response:
        """Make PUT request to Trello API"""
        url = f"https://api.trello.com/1/{endpoint}"
        all_data = {**self.base_params, **(data or {})}
        return requests.put(url, data=all_data, headers=HEADERS)
    
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
        "members": "true",
        "actions": "commentCard",
        "actions_limit": 1000
    })
    
    if response.status_code != 200:
        print(f"❌ Failed to fetch cards from board {board_id}: {response.text}")
        return []
    
    return response.json()

def get_all_cards_from_list(api: TrelloAPI, list_id: str) -> List[Dict]:
    """Get all cards from a specific list with full details"""
    response = api.get(f"lists/{list_id}/cards", {
        "attachments": "true",
        "checklists": "all",
        "members": "true",
        "actions": "commentCard",
        "actions_limit": 1000
    })
    
    if response.status_code != 200:
        print(f"❌ Failed to fetch cards from list {list_id}: {response.text}")
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

def find_card_by_name_and_desc(api: TrelloAPI, board_id: str, card_name: str, original_desc: str) -> Optional[Dict]:
    """Find a card on a board by name and original description content"""
    cards = get_all_cards_from_board(api, board_id)
    
    for card in cards:
        if card["name"] == card_name:
            # Check if the description contains the original description
            if original_desc in card.get("desc", ""):
                return card
    
    return None

def extract_mirror_metadata(description: str) -> Optional[Dict]:
    """Extract mirror metadata from card description"""
    if MIRROR_MARKER not in description:
        return None
    
    try:
        # Find the metadata JSON
        start = description.find(MIRROR_MARKER) + len(MIRROR_MARKER)
        end = description.find("\n", start)
        if end == -1:
            end = len(description)
        
        metadata_str = description[start:end].strip()
        return json.loads(metadata_str)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"⚠️  Failed to parse mirror metadata: {e}")
        return None

def create_mirror_metadata(source_board_id: str, source_card_id: str, original_desc: str) -> str:
    """Create mirror metadata to embed in card description"""
    metadata = {
        "source_board": source_board_id,
        "source_card": source_card_id,
        "original_desc": original_desc,
        "mirrored_at": datetime.utcnow().isoformat()
    }
    return f"{MIRROR_MARKER}{json.dumps(metadata)}"

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

def sync_card_changes(api: TrelloAPI, master_card: Dict, source_board_id: str, source_card_id: str, original_desc: str) -> bool:
    """Sync changes from master card back to source card"""
    print(f"🔄 Syncing changes for '{master_card['name']}' back to source...")
    
    # Get current source card
    source_response = api.get(f"cards/{source_card_id}", {
        "attachments": "true",
        "checklists": "all",
        "members": "true"
    })
    
    if source_response.status_code != 200:
        print(f"❌ Could not find source card {source_card_id}: {source_response.text}")
        return False
    
    source_card = source_response.json()
    
    # Update source card with changes from master
    updates = {}
    
    # Update name if changed
    if master_card["name"] != source_card["name"]:
        updates["name"] = master_card["name"]
    
    # Update description (remove mirror metadata and restore original)
    master_desc = master_card.get("desc", "")
    if MIRROR_MARKER in master_desc:
        # Extract the modified description (everything before the mirror marker)
        desc_end = master_desc.find(MIRROR_MARKER)
        clean_desc = master_desc[:desc_end].strip()
    else:
        clean_desc = master_desc
    
    if clean_desc != source_card.get("desc", ""):
        updates["desc"] = clean_desc
    
    # Update due date if changed
    if master_card.get("due") != source_card.get("due"):
        updates["due"] = master_card.get("due", "")
    
    # Apply basic updates
    if updates:
        response = api.put(f"cards/{source_card_id}", updates)
        if response.status_code != 200:
            print(f"❌ Failed to update source card: {response.text}")
            return False
    
    # Sync checklists
    sync_checklists(api, master_card, source_card_id)
    
    # Sync members
    sync_members(api, master_card, source_card, source_card_id)
    
    # Sync attachments
    sync_attachments(api, master_card, source_card, source_card_id)
    
    # Sync comments (non-bot comments)
    sync_comments(api, master_card, source_card_id)
    
    print(f"✅ Successfully synced changes for '{master_card['name']}'")
    return True

def sync_checklists(api: TrelloAPI, master_card: Dict, source_card_id: str):
    """Sync checklists from master card to source card"""
    # Get current source card checklists
    source_response = api.get(f"cards/{source_card_id}/checklists")
    if source_response.status_code != 200:
        return
    
    source_checklists = source_response.json()
    
    # Create a mapping of checklist names to IDs for the source card
    source_checklist_map = {cl["name"]: cl["id"] for cl in source_checklists}
    
    # Sync each checklist from master
    for master_checklist in master_card.get("checklists", []):
        checklist_name = master_checklist["name"]
        
        if checklist_name in source_checklist_map:
            # Update existing checklist
            source_checklist_id = source_checklist_map[checklist_name]
            
            # Get current checklist items
            source_cl_response = api.get(f"checklists/{source_checklist_id}")
            if source_cl_response.status_code != 200:
                continue
            
            source_cl = source_cl_response.json()
            source_items = {item["name"]: item for item in source_cl.get("checkItems", [])}
            
            # Update checklist items
            for master_item in master_checklist.get("checkItems", []):
                item_name = master_item["name"]
                item_state = master_item["state"]
                
                if item_name in source_items:
                    # Update existing item state
                    source_item = source_items[item_name]
                    if source_item["state"] != item_state:
                        api.put(f"cards/{source_card_id}/checkItem/{source_item['id']}", {
                            "state": item_state
                        })
                else:
                    # Add new item
                    api.post(f"checklists/{source_checklist_id}/checkItems", {
                        "name": item_name,
                        "checked": str(item_state == "complete").lower()
                    })

def sync_members(api: TrelloAPI, master_card: Dict, source_card: Dict, source_card_id: str):
    """Sync members from master card to source card"""
    master_members = set(master_card.get("idMembers", []))
    source_members = set(source_card.get("idMembers", []))
    
    # Add new members
    for member_id in master_members - source_members:
        api.post(f"cards/{source_card_id}/idMembers", {"value": member_id})
    
    # Remove members no longer on master
    for member_id in source_members - master_members:
        api.delete(f"cards/{source_card_id}/idMembers/{member_id}")

def sync_attachments(api: TrelloAPI, master_card: Dict, source_card: Dict, source_card_id: str):
    """Sync attachments from master card to source card"""
    master_attachments = {att.get("url", att.get("name", "")): att for att in master_card.get("attachments", [])}
    source_attachments = {att.get("url", att.get("name", "")): att for att in source_card.get("attachments", [])}
    
    # Add new attachments
    for att_key, attachment in master_attachments.items():
        if att_key not in source_attachments and attachment.get("url"):
            api.post(f"cards/{source_card_id}/attachments", {"url": attachment["url"]})

def sync_comments(api: TrelloAPI, master_card: Dict, source_card_id: str):
    """Sync non-bot comments from master card to source card"""
    master_comments = []
    
    # Get comments from master card
    for action in master_card.get("actions", []):
        if (action.get("type") == "commentCard" and 
            action.get("data", {}).get("text") and
            not action.get("data", {}).get("text", "").startswith(MIRROR_COMMENT_MARKER)):
            master_comments.append(action["data"]["text"])
    
    # Add comments to source card (Note: We can't easily check for duplicates without more complex logic)
    for comment in master_comments:
        api.post(f"cards/{source_card_id}/actions/comments", {"text": comment})

def sync_changes_from_master(api: TrelloAPI) -> int:
    """Sync changes from master board back to source boards"""
    print("\n🔄 Phase 1: Syncing changes from Master board back to source boards...")
    
    synced_count = 0
    
    # Process both master lists
    for list_id, board_name in [(MASTER_PROPOSALS_LIST_ID, "Proposals"), (MASTER_PAPERS_LIST_ID, "Papers")]:
        print(f"\n📋 Processing Master {board_name} list...")
        
        cards = get_all_cards_from_list(api, list_id)
        
        for card in cards:
            metadata = extract_mirror_metadata(card.get("desc", ""))
            
            if metadata:
                source_board_id = metadata.get("source_board")
                source_card_id = metadata.get("source_card")
                original_desc = metadata.get("original_desc", "")
                
                if source_board_id and source_card_id:
                    if sync_card_changes(api, card, source_board_id, source_card_id, original_desc):
                        synced_count += 1
                else:
                    print(f"⚠️  Invalid metadata for card '{card['name']}'")
            else:
                print(f"⚠️  No mirror metadata found for card '{card['name']}'")
    
    print(f"🔄 Phase 1 Complete: Synced {synced_count} cards back to source boards")
    return synced_count

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

def mirror_card(api: TrelloAPI, card: Dict, target_list_id: str, source_board_name: str, source_board_id: str) -> bool:
    """Mirror a card to the target list with all its properties and metadata"""
    original_desc = card.get("desc", "")
    
    # Create mirror metadata
    mirror_metadata = create_mirror_metadata(source_board_id, card["id"], original_desc)
    
    # Create the card with embedded metadata
    card_data = {
        "idList": target_list_id,
        "name": card["name"],
        "desc": f"{original_desc}\n\n{mirror_metadata}",
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
    
    # Add mirror comment
    api.post(f"cards/{new_card_id}/actions/comments", {
        "text": f"{MIRROR_COMMENT_MARKER} {source_board_name} board"
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
            if mirror_card(api, card, master_list_id, board_name, board_id):
                mirrored_count += 1
    
    print(f"📤 Mirrored {mirrored_count} cards from {board_name} board")
    return mirrored_count

def main():
    """Main execution function"""
    print("🚀 Starting Trello Card Bi-Directional Mirror Script")
    print(f"⏰ Started at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    # Initialize API
    api = TrelloAPI(TRELLO_API_KEY, TRELLO_TOKEN)
    
    # Phase 1: Sync changes from master back to source boards
    synced_count = sync_changes_from_master(api)
    
    # Phase 2: Clear master board lists and re-mirror
    print("\n🧹 Phase 2: Clearing Master Board lists...")
    clear_list(api, MASTER_PROPOSALS_LIST_ID, "Master Proposals")
    clear_list(api, MASTER_PAPERS_LIST_ID, "Master Papers")
    
    # Phase 3: Mirror qualifying cards from source boards
    print("\n📤 Phase 3: Mirroring qualifying cards to Master board...")
    total_mirrored = 0
    total_mirrored += process_board(api, PROPOSALS_BOARD_ID, "Proposals", MASTER_PROPOSALS_LIST_ID)
    total_mirrored += process_board(api, PAPERS_BOARD_ID, "Papers", MASTER_PAPERS_LIST_ID)
    
    print(f"\n🎉 Script completed successfully!")
    print(f"🔄 Cards synced back to source: {synced_count}")
    print(f"📤 Cards mirrored to master: {total_mirrored}")
    print(f"⏰ Finished at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")

if __name__ == "__main__":
    main()
