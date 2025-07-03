import os
import json
import pandas as pd
import requests
from datetime import datetime
from typing import List, Dict, Set, Optional

# Configuration
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
TRELLO_BOARD_ID = "68642fae07900e6d2d7d79bc"

class FundingSyncProcessor:
    def __init__(self, csv_path: str, keywords_path: str):
        self.csv_path = csv_path
        self.keywords_path = keywords_path
        self.keywords = self.load_keywords()
        
    def load_keywords(self) -> List[str]:
        """Load lab keywords from JSON file."""
        try:
            with open(self.keywords_path, 'r') as f:
                data = json.load(f)
                return data.get("lab_keywords", [])
        except FileNotFoundError:
            print(f"❌ Keywords file not found: {self.keywords_path}")
            return []
        except json.JSONDecodeError:
            print(f"❌ Invalid JSON in keywords file: {self.keywords_path}")
            return []
    
    def load_funding_csv(self) -> List[Dict]:
        """Load and parse the funding CSV file."""
        try:
            df = pd.read_csv(self.csv_path)
            entries = []
            
            for _, row in df.iterrows():
                # Extract link from HYPERLINK formula if present
                link_cell = str(row.get("OPPORTUNITY NUMBER", ""))
                if 'HYPERLINK' in link_cell and '"' in link_cell:
                    # Extract URL from HYPERLINK("url","text") format
                    link = link_cell.split('"')[1]
                else:
                    link = link_cell
                
                entry = {
                    "title": str(row.get("OPPORTUNITY TITLE", "")).strip(),
                    "description": str(row.get("FUNDING DESCRIPTION", "")).strip(),
                    "close_date": str(row.get("CLOSE DATE", "")).strip(),
                    "link": link.strip()
                }
                entries.append(entry)
            
            print(f"📊 Loaded {len(entries)} entries from CSV")
            return entries
            
        except FileNotFoundError:
            print(f"❌ CSV file not found: {self.csv_path}")
            return []
        except Exception as e:
            print(f"❌ Error loading CSV: {e}")
            return []
    
    def is_future_entry(self, entry: Dict) -> bool:
        """Check if the entry's close date is in the future."""
        try:
            close_date = datetime.strptime(entry["close_date"], "%m/%d/%Y")
            return close_date >= datetime.today()
        except ValueError:
            # Try alternative date formats
            for fmt in ["%m/%d/%y", "%Y-%m-%d", "%d/%m/%Y"]:
                try:
                    close_date = datetime.strptime(entry["close_date"], fmt)
                    return close_date >= datetime.today()
                except ValueError:
                    continue
            print(f"⚠️ Could not parse date: {entry['close_date']} for {entry['title']}")
            return False
    
    def contains_keyword(self, entry: Dict) -> bool:
        """Check if entry contains any of the lab keywords."""
        if not self.keywords:
            return False
            
        text = (entry["title"] + " " + entry["description"]).lower()
        matched_keywords = [k for k in self.keywords if k.lower() in text]
        
        if matched_keywords:
            print(f"🎯 Matched keywords for '{entry['title'][:50]}...': {matched_keywords[:3]}")
        
        return len(matched_keywords) > 0
    
    def filter_entries(self, entries: List[Dict]) -> tuple:
        """Filter entries into semi-filtered and dummy lists."""
        semi_filtered = []
        dummy_filtered = []
        skipped_past = 0
        
        for entry in entries:
            if not self.is_future_entry(entry):
                skipped_past += 1
                continue
                
            if self.contains_keyword(entry):
                semi_filtered.append(entry)
            else:
                dummy_filtered.append(entry)
        
        print(f"📅 Skipped {skipped_past} entries with past due dates")
        print(f"🔎 Semi-Filtered Matches: {len(semi_filtered)}")
        print(f"📄 Dummy (Unmatched): {len(dummy_filtered)}")
        
        return semi_filtered, dummy_filtered


class TrelloManager:
    def __init__(self):
        self.api_key = TRELLO_API_KEY
        self.token = TRELLO_TOKEN
        self.board_id = TRELLO_BOARD_ID
        
        if not self.api_key or not self.token:
            raise ValueError("❌ Trello API key and token must be set as environment variables")
    
    def get_list_id_by_name(self, list_name: str) -> Optional[str]:
        """Find or create a Trello list by name on the board."""
        url = f"https://api.trello.com/1/boards/{self.board_id}/lists"
        params = {
            "key": self.api_key,
            "token": self.token
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            lists = response.json()
            
            # Check if list exists
            for lst in lists:
                if lst["name"].lower() == list_name.lower():
                    return lst["id"]
            
            # Create list if it doesn't exist
            return self.create_list(list_name)
            
        except requests.RequestException as e:
            print(f"❌ Error fetching Trello lists: {e}")
            return None
    
    def create_list(self, list_name: str) -> Optional[str]:
        """Create a new Trello list."""
        url = "https://api.trello.com/1/lists"
        params = {
            "name": list_name,
            "idBoard": self.board_id,
            "key": self.api_key,
            "token": self.token
        }
        
        try:
            response = requests.post(url, params=params)
            response.raise_for_status()
            print(f"🆕 Created new list: {list_name}")
            return response.json()["id"]
            
        except requests.RequestException as e:
            print(f"❌ Error creating list '{list_name}': {e}")
            return None
    
    def get_existing_card_titles(self, list_id: str) -> Set[str]:
        """Return a set of card titles already on the list."""
        url = f"https://api.trello.com/1/lists/{list_id}/cards"
        params = {
            "key": self.api_key,
            "token": self.token,
            "fields": "name"
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            cards = response.json()
            return set(card["name"].strip().lower() for card in cards)
            
        except requests.RequestException as e:
            print(f"❌ Error fetching existing cards: {e}")
            return set()
    
    def create_card(self, entry: Dict, list_name: str) -> bool:
        """Create a Trello card with due date and description."""
        list_id = self.get_list_id_by_name(list_name)
        if not list_id:
            print(f"🚫 Skipping card due to list fetch failure: {entry['title']}")
            return False
        
        existing_titles = self.get_existing_card_titles(list_id)
        title = entry["title"].strip()
        normalized_title = title.lower()
        
        if normalized_title in existing_titles:
            print(f"⏭️ Skipping duplicate: {title}")
            return False
        
        # Prepare card data
        description = entry.get("description", "")
        link = entry.get("link", "")
        full_desc = f"{description}\n\nLink: {link}" if link else description
        
        # Parse due date
        due_date = None
        try:
            due_date = datetime.strptime(entry["close_date"], "%m/%d/%Y").isoformat()
        except ValueError:
            for fmt in ["%m/%d/%y", "%Y-%m-%d", "%d/%m/%Y"]:
                try:
                    due_date = datetime.strptime(entry["close_date"], fmt).isoformat()
                    break
                except ValueError:
                    continue
        
        # Create card
        url = "https://api.trello.com/1/cards"
        params = {
            "key": self.api_key,
            "token": self.token,
            "idList": list_id,
            "name": title,
            "desc": full_desc,
            "due": due_date
        }
        
        try:
            response = requests.post(url, params=params)
            response.raise_for_status()
            print(f"✅ Created card: {title}")
            return True
            
        except requests.RequestException as e:
            print(f"❌ Failed to create card '{title}': {e}")
            return False


def main():
    # Configuration
    csv_path = "CSV/grants-gov-opp-search--20250702135040.csv"
    keywords_path = "modules/funding_sync/keywords.json"
    
    print("🚀 Starting Funding Sync Process...")
    
    # Initialize processor and manager
    processor = FundingSyncProcessor(csv_path, keywords_path)
    trello_manager = TrelloManager()
    
    # Load and process data
    funding_entries = processor.load_funding_csv()
    if not funding_entries:
        print("❌ No funding entries loaded. Exiting.")
        return
    
    # Filter entries
    semi_filtered, dummy_filtered = processor.filter_entries(funding_entries)
    
    # Create Trello cards
    print("\n📝 Creating Trello cards...")
    
    created_semi = 0
    created_dummy = 0
    
    # Process semi-filtered entries
    for entry in semi_filtered:
        if trello_manager.create_card(entry, "Semi-Filtered"):
            created_semi += 1
    
    # Process dummy entries
    for entry in dummy_filtered:
        if trello_manager.create_card(entry, "Dummy List"):
            created_dummy += 1
    
    print(f"\n🎉 Process Complete!")
    print(f"✅ Created {created_semi} cards in Semi-Filtered list")
    print(f"✅ Created {created_dummy} cards in Dummy List")
    print(f"📊 Total cards created: {created_semi + created_dummy}")


if __name__ == "__main__":
    main()