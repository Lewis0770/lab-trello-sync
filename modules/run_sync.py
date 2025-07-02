#!/usr/bin/env python3
"""
Slack to Trello Sync Runner
Run this script to sync messages from Slack to Trello cards
"""

import os
import sys
from modules.slack_to_trello import process_slack_messages
from modules.card_creator import test_trello_connection

def main():
    """Main function to run the Slack to Trello sync"""
    print("🚀 Starting Slack to Trello sync...")
    print("=" * 50)
    
    # Test Trello connection first
    print("🔧 Testing Trello connection...")
    if not test_trello_connection():
        print("❌ Cannot connect to Trello. Please check your API credentials.")
        sys.exit(1)
    
    print("✅ Trello connection successful!")
    print("-" * 30)
    
    # Process Slack messages
    try:
        print("📱 Processing Slack messages...")
        process_slack_messages()
        print("-" * 30)
        print("🎉 Sync completed successfully!")
        
    except Exception as e:
        print(f"❌ Sync failed with error: {e}")
        print("Please check your Slack bot permissions and channel access.")
        sys.exit(1)

if __name__ == "__main__":
    main()