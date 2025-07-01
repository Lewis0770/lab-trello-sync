import os
import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from modules.slack_parser import parse_funding_text
from modules.card_creator import get_or_create_list, create_card

# Load Slack token and channel ID from environment
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = "C093Y4SS3TN"

if not SLACK_BOT_TOKEN or not SLACK_CHANNEL_ID:
    raise EnvironmentError("Missing Slack bot token or channel ID in environment variables.")

client = WebClient(token=SLACK_BOT_TOKEN)

def process_slack_messages():
    try:
        response = client.conversations_history(channel=SLACK_CHANNEL_ID, limit=5)
        messages = response.get("messages", [])

        for msg in messages:
            reactions = msg.get("reactions", [])
            if any(r.get("name") == "white_check_mark" for r in reactions):
                continue  # Skip already processed messages

            text = msg.get("text", "")
            if not text.strip():
                continue

            parsed = parse_funding_text(text)

            list_id = get_or_create_list(parsed["list_title"])
            for card in parsed["cards"]:
                create_card(
                    list_id=list_id,
                    name=card["title"],
                    desc=card["description"],
                    attachments=card["attachments"]
                )

            # Mark as processed
            client.reactions_add(
                channel=SLACK_CHANNEL_ID,
                name="white_check_mark",
                timestamp=msg["ts"]
            )

    except SlackApiError as e:
        print(f"Slack API Error: {e.response['error']}")
    except Exception as e:
        print(f"Error: {e}")
