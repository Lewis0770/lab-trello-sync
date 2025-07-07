# modules/mirror_priority_cards.py
import os
import requests

trello_key = os.getenv("TRELLO_API_KEY")
trello_token = os.getenv("TRELLO_TOKEN")

# Board IDs
PROPOSALS_BOARD = "6860242608fdc9ecc66f793b"
PAPERS_BOARD = "6866dd4609df4573a20ba546"
MASTER_BOARD = "685c44d7f65b2a102409f67b"

# List IDs on MASTER board
MASTER_PROPOSALS_LIST = "685d5ad92a6725cdeb415f91"
MASTER_PAPERS_LIST = "685d5ad7a89f68ae6d215449"

PRIORITY_LIST_NAME = "Priority IV"
CHECKLIST_NAME = "In-Progress"


def get_list_id(board_id, name):
    url = f"https://api.trello.com/1/boards/{board_id}/lists"
    params = {"key": trello_key, "token": trello_token}
    res = requests.get(url, params=params)
    for lst in res.json():
        if lst["name"] == name:
            return lst["id"]
    return None


def get_cards(board_id, list_id):
    url = f"https://api.trello.com/1/lists/{list_id}/cards"
    params = {"key": trello_key, "token": trello_token, "fields": "name,idChecklists,labels,idMembers,due,desc,attachments"}
    res = requests.get(url, params=params)
    return res.json()


def get_checklist_completion(card):
    for checklist_id in card.get("idChecklists", []):
        checklist_url = f"https://api.trello.com/1/checklists/{checklist_id}"
        checklist = requests.get(checklist_url, params={"key": trello_key, "token": trello_token}).json()
        if checklist.get("name") == CHECKLIST_NAME:
            total = len(checklist.get("checkItems", []))
            if total == 0:
                return 0
            done = sum(1 for item in checklist["checkItems"] if item["state"] == "complete")
            return int((done / total) * 100)
    return 0


def clear_master_list(list_id):
    url = f"https://api.trello.com/1/lists/{list_id}/cards"
    res = requests.get(url, params={"key": trello_key, "token": trello_token})
    for card in res.json():
        delete_url = f"https://api.trello.com/1/cards/{card['id']}"
        requests.delete(delete_url, params={"key": trello_key, "token": trello_token})


def mirror_card(card, target_list_id):
    card_data = {
        "key": trello_key,
        "token": trello_token,
        "idList": target_list_id,
        "name": card["name"],
        "desc": card.get("desc", "") + "\n\nMirrored by bot.",
        "due": card.get("due")
    }
    create_url = "https://api.trello.com/1/cards"
    res = requests.post(create_url, params=card_data).json()
    new_id = res["id"]

    # Mirror labels
    for label in card.get("labels", []):
        label_url = f"https://api.trello.com/1/cards/{new_id}/idLabels"
        requests.post(label_url, params={"key": trello_key, "token": trello_token, "value": label["id"]})

    # Mirror members
    for member in card.get("idMembers", []):
        mem_url = f"https://api.trello.com/1/cards/{new_id}/idMembers"
        requests.post(mem_url, params={"key": trello_key, "token": trello_token, "value": member})

    return res


def main():
    sources = [
        (PROPOSALS_BOARD, MASTER_PROPOSALS_LIST),
        (PAPERS_BOARD, MASTER_PAPERS_LIST)
    ]

    for board_id, master_list in sources:
        list_id = get_list_id(board_id, PRIORITY_LIST_NAME)
        if not list_id:
            print(f"❌ Couldn't find Priority IV in board {board_id}")
            continue

        cards = get_cards(board_id, list_id)

        # Wipe current cards in the master list before re-mirroring
        clear_master_list(master_list)

        for card in cards:
            progress = get_checklist_completion(card)
            if progress >= 75:
                mirror_card(card, master_list)


if __name__ == "__main__":
    main()
