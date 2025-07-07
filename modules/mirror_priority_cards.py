# mirror_priority_cards.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()

# Hardcoded board and list info
PROPOSALS_BOARD_ID = "6862042608fdc9ecc66f793b"
PAPERS_BOARD_ID = "6866dd4609df4573a20ba546"
MASTER_BOARD_ID = "685c44d7f65b2a102409f67b"
MASTER_PROPOSALS_LIST_ID = "685d5ad92a6725cdeb415f91"
MASTER_PAPERS_LIST_ID = "685d5ad7a89f68ae6d215449"
PRIORITY_LIST_NAME = "Priority IV"

TRELLO_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")

def get_list_id(board_id, list_name):
    url = f"https://api.trello.com/1/boards/{board_id}/lists"
    query = {"key": TRELLO_KEY, "token": TRELLO_TOKEN}
    res = requests.get(url, params=query)

    print(f"Request URL: {res.url}")
    print(f"Status Code: {res.status_code}")
    print(f"Raw Response:\n{res.text}\n")

    if res.status_code != 200:
        raise Exception("Failed to fetch lists")

    try:
        lists = res.json()
    except Exception as e:
        print("[ERROR] JSON decode failed.")
        raise e

    for lst in lists:
        if lst['name'] == list_name:
            return lst['id']

    raise ValueError(f"List '{list_name}' not found on board {board_id}")

def get_cards_in_list(list_id):
    url = f"https://api.trello.com/1/lists/{list_id}/cards"
    query = {"key": TRELLO_KEY, "token": TRELLO_TOKEN, "checklists": "all"}
    return requests.get(url, params=query).json()

def mirror_card(card, dest_list_id):
    url = "https://api.trello.com/1/cards"
    data = {
        "idList": dest_list_id,
        "name": card["name"],
        "desc": card["desc"],
        "key": TRELLO_KEY,
        "token": TRELLO_TOKEN,
        "due": card.get("due")
    }
    new_card = requests.post(url, data=data).json()

    if "id" not in new_card:
        print(f"Failed to create card: {new_card}")
        return

    # Mirror members
    for member_id in card.get("idMembers", []):
        requests.post(f"https://api.trello.com/1/cards/{new_card['id']}/idMembers",
                      data={"value": member_id, "key": TRELLO_KEY, "token": TRELLO_TOKEN})

    # Mirror labels
    for label_id in card.get("idLabels", []):
        requests.post(f"https://api.trello.com/1/cards/{new_card['id']}/idLabels",
                      data={"value": label_id, "key": TRELLO_KEY, "token": TRELLO_TOKEN})

    # Mirror attachments
    for attachment in card.get("attachments", []):
        requests.post(f"https://api.trello.com/1/cards/{new_card['id']}/attachments",
                      data={"url": attachment['url'], "key": TRELLO_KEY, "token": TRELLO_TOKEN})

    # Mirror checklist if present
    for checklist in card.get("checklists", []):
        checklist_res = requests.post(f"https://api.trello.com/1/cards/{new_card['id']}/checklists",
            data={"name": checklist['name'], "key": TRELLO_KEY, "token": TRELLO_TOKEN})

        checklist_id = checklist_res.json().get("id")
        for item in checklist["checkItems"]:
            requests.post(f"https://api.trello.com/1/checklists/{checklist_id}/checkItems",
                data={"name": item['name'], "checked": str(item['state'] == 'complete').lower(),
                      "key": TRELLO_KEY, "token": TRELLO_TOKEN})

    # Add comment noting the card was mirrored
    requests.post(f"https://api.trello.com/1/cards/{new_card['id']}/actions/comments",
                  data={"text": "[Bot] Mirrored from source board.", "key": TRELLO_KEY, "token": TRELLO_TOKEN})

def mirror_board(board_id, master_list_id):
    list_id = get_list_id(board_id, PRIORITY_LIST_NAME)
    cards = get_cards_in_list(list_id)
    for card in cards:
        checklist_completion = [
            (item['state'] == 'complete')
            for checklist in card.get('checklists', [])
            for item in checklist.get('checkItems', [])
        ]
        if checklist_completion:
            percent_complete = sum(checklist_completion) / len(checklist_completion)
        else:
            percent_complete = 0

        if percent_complete >= 0.75:
            mirror_card(card, master_list_id)


def main():
    mirror_board(PROPOSALS_BOARD_ID, MASTER_PROPOSALS_LIST_ID)
    mirror_board(PAPERS_BOARD_ID, MASTER_PAPERS_LIST_ID)

if __name__ == "__main__":
    main()
