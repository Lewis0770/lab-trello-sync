# mirror_funding_cards.py
import os
import requests
from datetime import datetime

TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")

PROPOSALS_BOARD_ID = "6860242608fdc9ecc66f793b"
PAPERS_BOARD_ID = "6866dd4609df4573a20ba546"
MASTER_BOARD_ID = "685c44d7f65b2a102409f67b"
MASTER_PROPOSALS_LIST_ID = "685d5ad92a6725cdeb415f91"
MASTER_PAPERS_LIST_ID = "685d5ad7a89f68ae6d215449"

HEADERS = {"Accept": "application/json"}

def get_cards(board_id):
    url = f"https://api.trello.com/1/boards/{board_id}/cards"
    params = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN, "cards": "open", "attachments": "true"}
    return requests.get(url, params=params, headers=HEADERS).json()

def get_checklist_progress(card_id):
    url = f"https://api.trello.com/1/cards/{card_id}/checklists"
    params = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}
    response = requests.get(url, params=params)
    if response.status_code != 200:
        return 0
    data = response.json()
    for checklist in data:
        if checklist['name'].lower() == "in-progress":
            total = len(checklist['checkItems'])
            done = len([item for item in checklist['checkItems'] if item['state'] == 'complete'])
            if total > 0:
                return int((done / total) * 100)
    return 0

def get_list_name(card):
    url = f"https://api.trello.com/1/lists/{card['idList']}"
    params = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}
    return requests.get(url, params=params).json().get("name", "")

def delete_cards_from_list(list_id):
    url = f"https://api.trello.com/1/lists/{list_id}/cards"
    params = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}
    cards = requests.get(url, params=params).json()
    for card in cards:
        del_url = f"https://api.trello.com/1/cards/{card['id']}"
        requests.delete(del_url, params=params)

    print(f"🧹 Cleared list {list_id} with {len(cards)} cards.")

def mirror_card(card, target_list_id):
    url = "https://api.trello.com/1/cards"
    params = {
        "key": TRELLO_API_KEY,
        "token": TRELLO_TOKEN,
        "idList": target_list_id,
        "name": card["name"],
        "desc": card["desc"] + f"\n\nMirrored from [{card['idBoard']}] on {datetime.utcnow().strftime('%Y-%m-%d')}.",
        "due": card.get("due") or ""
    }
    response = requests.post(url, params=params)
    if response.status_code == 200:
        print(f"✅ Mirrored: {card['name']}")
    else:
        print(f"❌ Failed: {card['name']} — {response.text}")

def process_board(board_id, master_list_id):
    cards = get_cards(board_id)
    for card in cards:
        checklist_percent = get_checklist_progress(card["id"])
        list_name = get_list_name(card)

        if checklist_percent >= 75 or list_name.strip().lower() == "priority iv":
            mirror_card(card, master_list_id)

if __name__ == '__main__':
    print("🚀 Clearing Master Board lists...")
    delete_cards_from_list(MASTER_PROPOSALS_LIST_ID)
    delete_cards_from_list(MASTER_PAPERS_LIST_ID)

    print("📤 Syncing Proposals...")
    process_board(PROPOSALS_BOARD_ID, MASTER_PROPOSALS_LIST_ID)

    print("📤 Syncing Papers...")
    process_board(PAPERS_BOARD_ID, MASTER_PAPERS_LIST_ID)

    print("✅ Done.")
