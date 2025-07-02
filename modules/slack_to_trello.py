import os
import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from modules.slack_parser import parse_funding_text
from modules.card_creator import get_or_create_list, create_card

# Load Slack token and channel ID from environment
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID", "C093Y4SS3TN")  # Default or from env

if not SLACK_BOT_TOKEN:
    raise EnvironmentError("Missing SLACK_BOT_TOKEN in environment variables.")

client = WebClient(token=SLACK_BOT_TOKEN)

def process_slack_messages():
    """Process recent Slack messages and create Trello cards"""
    try:
        print("🔍 Fetching Slack messages...")
        response = client.conversations_history(channel=SLACK_CHANNEL_ID, limit=10)
        messages = response.get("messages", [])
        
        if not messages:
            print("No messages found in channel.")
            return

        processed_count = 0
        
        for msg in messages:
            # Skip messages that are already processed (have checkmark reaction)
            reactions = msg.get("reactions", [])
            if any(r.get("name") == "white_check_mark" for r in reactions):
                print(f"⏭️ Skipping already processed message: {msg.get('text', '')[:50]}...")
                continue

            text = msg.get("text", "")
            if not text.strip():
                print("⏭️ Skipping empty message")
                continue

            print(f"📝 Processing message: {text[:100]}...")
            
            try:
                # Parse the message
                parsed = parse_funding_text(text)
                
                if not parsed["cards"]:
                    print("⚠️ No cards found in message, skipping...")
                    continue
                
                print(f"✅ Parsed {len(parsed['cards'])} cards from: '{parsed['list_title']}'")

                # Create or get the Trello list
                list_id = get_or_create_list(parsed["list_title"])
                print(f"📋 Using Trello list: {parsed['list_title']}")

                # Create cards
                for card in parsed["cards"]:
                    try:
                        created_card = create_card(
                            list_id=list_id,
                            name=card["title"],
                            desc=card["description"],
                            attachments=card["attachments"]
                        )
                        print(f"✅ Created card: '{card['title']}'")
                        if card["attachments"]:
                            print(f"   📎 Added {len(card['attachments'])} attachments")
                    except Exception as card_error:
                        print(f"❌ Failed to create card '{card['title']}': {card_error}")

                # Mark message as processed
                try:
                    client.reactions_add(
                        channel=SLACK_CHANNEL_ID,
                        name="white_check_mark",
                        timestamp=msg["ts"]
                    )
                    print("✅ Marked message as processed")
                    processed_count += 1
                except Exception as reaction_error:
                    print(f"⚠️ Could not add reaction: {reaction_error}")

            except Exception as parse_error:
                print(f"❌ Failed to parse message: {parse_error}")
                continue

        print(f"🎉 Processed {processed_count} new messages")

    except SlackApiError as e:
        print(f"❌ Slack API Error: {e.response['error']}")
        raise
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        raise

if __name__ == "__main__":
    process_slack_messages()