import os
import requests
from typing import List, Dict
from modules.slack_parser import parse_funding_text

# --- Environment variables / tokens
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")

TRELLO_BOARD_ID = "68642fae07900e6d2d7d79bc"
SLACK_CHANNEL_ID = "C093Y4SS3TN"  # Replace with your channel ID

# --- Trello Helpers
def get_or_create_list(list_name: str) -> str:
    url = f"https://api.trello.com/1/boards/{TRELLO_BOARD_ID}/lists"
    params = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}
    res = requests.get(url, params=params)
    res.raise_for_status()
    for lst in res.json():
        if lst["name"].strip().lower() == list_name.strip().lower():
            return lst["id"]

    # List not found, create new
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

# --- Slack Helper
def fetch_latest_slack_message() -> str:
    url = "https://slack.com/api/conversations.history"
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}"
    }
    params = {
        "channel": SLACK_CHANNEL_ID,
        "limit": 3
    }
    res = requests.get(url, headers=headers, params=params)
    res.raise_for_status()
    data = res.json()

    if not data.get("ok"):
        raise Exception(f"Slack API error: {data.get('error')}")

    messages = data.get("messages", [])
    return messages[0]["text"] if messages else None

# --- Orchestration
def main():
    print("🟡 Bot is scanning Slack messages...")

    messages = fetch_latest_slack_messages(limit=5)
    if not messages:
        print("No messages found.")
        return

    for msg in messages:
        if not msg.get("text"):
            continue

        print(f"🔍 Checking message: {msg['text'][:60]}...")

        try:
            parsed = parse_funding_text(msg["text"])
            print(f"✅ Parsed successfully: {parsed}")

            list_id = get_or_create_list(parsed["list_title"])
            for card in parsed["cards"]:
                create_card(list_id, card["title"], card["description"], card["attachments"])
                print(f"📌 Created card: {card['title']}")

        except Exception as e:
            print(f"⚠️ Failed to parse or create card from message: {e}")
