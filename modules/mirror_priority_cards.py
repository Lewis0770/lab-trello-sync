import requests
import os

# --- HARDCODED Trello credentials ---
API_KEY = "your_trello_api_key"
TOKEN = "your_trello_token"

# --- HARDCODED board/list IDs ---
PROPOSALS_BOARD_ID = "6862042608fdc9ecc66f793b"
PAPERS_BOARD_ID = "6866dd4609df4573a20ba546"
MASTER_BOARD_ID = "685c44d7f65b2a102409f67b"

MASTER_PROPOSALS_LIST_ID = "685d5ad92a6725cdeb415f91"
MASTER_PAPERS_LIST_ID = "685d5ad7a89f68ae6d215449"

PRIORITY_LIST_NAME = "Priority IV"

# --- Trello API helpers ---
def get_list_id(board_id, target_name):
    url = f"https://api.trello.com/1/boards/{board_id}/lists"
    res = requests.get(url, params={"key": API_KEY, "token": TOKEN})
    if res.status_code != 200:
        print(f"Request URL: {url}")
        print(f"Status Code: {res.status_code}")
        print("Raw Response:", res.text)
        raise Exception("Failed to fetch lists")
    for lst in res.json():
        if lst["name"] == target_name:
            return lst["id"]
    raise Exception(f"List '{target_name}' not found on board {board_id}")

def get_cards(list_id):
    url = f"https://api.trello.com/1/lists/{list_id}/cards"
    res = requests.get(url, params={"key": API_KEY, "token": TOKEN, "checklists": "all", "fields": "all", "customFieldItems": "true"})
    return res.json()

def get_card_checklists(card_id):
    url = f"https://api.trello.com/1/cards/{card_id}/checklists"
    res = requests.get(url, params={"key": API_KEY, "token": TOKEN})
    return res.json()

def mirror_card(card, dest_list_id):
    url = "https://api.trello.com/1/cards"
    payload = {
        "name": card["name"],
        "desc": card["desc"],
        "idList": dest_list_id,
        "due": card["due"],
        "idLabels": ",".join(label["id"] for label in card["labels"]),
        "idMembers": ",".join(card["idMembers"]),
        "key": API_KEY,
        "token": TOKEN
    }
    res = requests.post(url, params=payload)
    if res.status_code == 200:
        card_id = res.json()["id"]
        requests.post(f"https://api.trello.com/1/cards/{card_id}/actions/comments", params={
            "key": API_KEY,
            "token": TOKEN,
            "text": f"Mirrored from card {card['shortUrl']}"
        })
    else:
        print("Failed to mirror card:", card["name"], res.text)

def mirror_board(board_id, dest_list_id):
    list_id = get_list_id(board_id, PRIORITY_LIST_NAME)
    cards = get_cards(list_id)
    for card in cards:
        # Skip if card has 'Completed' label
        has_completed_label = any(label.get("name", "").lower() == "completed" for label in card.get("labels", []))
        if has_completed_label:
            continue

        # Calculate checklist completion
        checklists = get_card_checklists(card["id"])
        total_items = sum(len(cl["checkItems"]) for cl in checklists)
        checked_items = sum(
            sum(1 for item in cl["checkItems"] if item["state"] == "complete")
            for cl in checklists
        )
        checklist_percent = (checked_items / total_items * 100) if total_items else 0

        if checklist_percent >= 75 or card["idList"] == list_id:
            mirror_card(card, dest_list_id)

def main():
    mirror_board(PROPOSALS_BOARD_ID, MASTER_PROPOSALS_LIST_ID)
    mirror_board(PAPERS_BOARD_ID, MASTER_PAPERS_LIST_ID)

if __name__ == "__main__":
    main()
