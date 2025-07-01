import os
import requests
from typing import List, Dict

TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
TRELLO_BOARD_ID = "68642fae07900e6d2d7d79bc"

def get_or_create_list(list_name: str) -> str:
    """Return Trello list ID, creating the list if it doesn’t exist"""
    url = f"https://api.trello.com/1/boards/{TRELLO_BOARD_ID}/lists"
    params = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}
    res = requests.get(url, params=params)
    res.raise_for_status()
    for lst in res.json():
        if lst["name"].strip().lower() == list_name.strip().lower():
            return lst["id"]

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
    return res.json()["id"]

def create_card(list_id: str, name: str, desc: str, attachments: List[str]) -> Dict:
    """Create a Trello card and return its response"""
    url = "https://api.trello.com/1/cards"
    data = {
        "key": TRELLO_API_KEY,
        "token": TRELLO_TOKEN,
        "idList": list_id,
        "name": name,
        "desc": desc
    }
    res = requests.post(url, data=data)
    res.raise_for_status()
    card = res.json()

    for link in attachments:
        attach_url = f"https://api.trello.com/1/cards/{card['id']}/attachments"
        attach_data = {
            "key": TRELLO_API_KEY,
            "token": TRELLO_TOKEN,
            "url": link
        }
        requests.post(attach_url, data=attach_data) 

    return card
