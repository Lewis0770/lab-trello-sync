import os
import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from modules.slack_parser import parse_funding_text
from modules.trello import get_or_create_list, create_card

# Load Slack token and channel ID from environment
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID")

client = WebClient(token=SLACK_BOT_TOKEN)

def process_slack_messages():
    try:
        # Fetch last 5 messages from the channel
        response = client.conversations_history(channel=SLACK_CHANNEL_ID, limit=5)
        messages = response["messages"]

        for msg in messages:
            reactions = msg.get("reactions", [])
            if any(r["name"] == "white_check_mark" for r in reactions):
                continue  # Skip already processed messages

            text = msg.get("text", "")
            parsed = parse_funding_text(text)

            list_id = get_or_create_list(parsed["list_title"])
            for card in parsed["cards"]:
                create_card(
                    list_id=list_id,
                    name=card["title"],
                    desc=card["description"],
                    attachments=card["attachments"]
                )

            # Mark message as processed with a ✅
            client.reactions_add(
                channel=SLACK_CHANNEL_ID,
                name="white_check_mark",
                timestamp=msg["ts"]
            )

    except SlackApiError as e:
        print(f"Slack API Error: {e.response['error']}")
    except Exception as e:
        print(f"Error: {e}")
