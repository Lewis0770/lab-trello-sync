#!/usr/bin/env python3
"""
Auto-manage Trello cards for Papers and Proposals boards.
- Moves overdue cards (>=3 days) to next Monday
- Marks cards with "Completed:" tag as completed
- Handles multiple boards: Papers and Proposals
"""

import os
import sys
import logging
import requests
import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TrelloClient:
    """Simple Trello API client."""
    
    def __init__(self, api_key: str, token: str):
        self.api_key = api_key
        self.token = token
        self.base_url = "https://api.trello.com/1"
        
    def _make_request(self, method: str, endpoint: str, params: Dict = None, data: Dict = None) -> Dict:
        """Make a request to the Trello API."""
        url = f"{self.base_url}/{endpoint}"
        
        # Add authentication to all requests
        if params is None:
            params = {}
        params.update({
            'key': self.api_key,
            'token': self.token
        })
        
        try:
            if method.upper() == 'GET':
                response = requests.get(url, params=params)
            elif method.upper() == 'PUT':
                response = requests.put(url, params=params, json=data)
            elif method.upper() == 'POST':
                response = requests.post(url, params=params, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
                
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise
    
    def get_boards(self) -> List[Dict]:
        """Get all boards for the authenticated user."""
        return self._make_request('GET', 'members/me/boards')
    
    def get_board_cards(self, board_id: str) -> List[Dict]:
        """Get all cards from a board."""
        return self._make_request('GET', f'boards/{board_id}/cards')
    
    def get_board_lists(self, board_id: str) -> List[Dict]:
        """Get all lists from a board."""
        return self._make_request('GET', f'boards/{board_id}/lists')
    
    def update_card_due_date(self, card_id: str, due_date: str) -> Dict:
        """Update a card's due date."""
        return self._make_request('PUT', f'cards/{card_id}', data={'due': due_date})
    
    def update_card_closed(self, card_id: str, closed: bool) -> Dict:
        """Update a card's closed status."""
        return self._make_request('PUT', f'cards/{card_id}', data={'closed': closed})
    
    def move_card_to_list(self, card_id: str, list_id: str) -> Dict:
        """Move a card to a different list."""
        return self._make_request('PUT', f'cards/{card_id}', data={'idList': list_id})

class CardAutoManager:
    def __init__(self, api_key: str, token: str, board_names: List[str] = ["Papers", "Proposals"], dry_run: bool = False):
        """Initialize the card auto-manager."""
        self.trello = TrelloClient(api_key, token)
        self.board_names = board_names
        self.boards = {}
        self.dry_run = dry_run
        self.stats = {
            'cards_processed': 0,
            'cards_moved_to_monday': 0,
            'cards_marked_completed': 0,
            'errors': 0,
            'boards_processed': 0
        }
        
        if self.dry_run:
            logger.info("Running in DRY-RUN mode - no changes will be made")
        
    def get_boards(self):
        """Get the target boards."""
        try:
            all_boards = self.trello.get_boards()
            found_boards = []
            
            for board in all_boards:
                if board['name'] in self.board_names:
                    self.boards[board['name']] = board
                    found_boards.append(board['name'])
                    logger.info(f"Found board: {board['name']}")
            
            missing_boards = set(self.board_names) - set(found_boards)
            if missing_boards:
                logger.warning(f"Could not find boards: {', '.join(missing_boards)}")
            
            if not found_boards:
                logger.error("No target boards found")
                return False
                
            logger.info(f"Will process {len(found_boards)} boards: {', '.join(found_boards)}")
            return True
            
        except Exception as e:
            logger.error(f"Error getting boards: {e}")
            return False
    
    def get_next_monday(self) -> datetime:
        """Get the date of the next Monday."""
        today = datetime.now()
        days_ahead = 0 - today.weekday()  # Monday is 0
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
        return today + timedelta(days=days_ahead)
    
    def is_overdue_by_days(self, due_date_str: str, days: int = 3) -> bool:
        """Check if a card is overdue by the specified number of days."""
        try:
            due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
            # Convert to local time for comparison
            due_date = due_date.replace(tzinfo=None)
            now = datetime.now()
            
            return (now - due_date).days >= days
            
        except (ValueError, AttributeError) as e:
            logger.warning(f"Error parsing due date '{due_date_str}': {e}")
            return False
    
    def has_completed_tag(self, card: dict) -> bool:
        """Check if card has a 'Completed:' tag."""
        labels = card.get('labels', [])
        for label in labels:
            if label.get('name', '').startswith('Completed'):
                return True
        return False
    
    def move_card_to_monday(self, card: dict, board_name: str) -> bool:
        """Move card's due date to next Monday."""
        try:
            next_monday = self.get_next_monday()
            due_date_str = next_monday.isoformat()
            
            if self.dry_run:
                logger.info(f"[DRY-RUN] Would move card '{card['name']}' in board '{board_name}' due date to {due_date_str}")
                return True
            
            # Update card due date
            self.trello.update_card_due_date(card['id'], due_date_str)
            
            logger.info(f"Moved card '{card['name']}' in board '{board_name}' due date to {due_date_str}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating due date for card '{card['name']}' in board '{board_name}': {e}")
            return False
    
    def mark_card_completed(self, card: dict, board_name: str) -> bool:
        """Mark card as completed by moving to appropriate list."""
        try:
            if self.dry_run:
                logger.info(f"[DRY-RUN] Would mark card '{card['name']}' in board '{board_name}' as completed")
                return True
            
            # Get all lists on the board
            board = self.boards[board_name]
            lists = self.trello.get_board_lists(board['id'])
            
            # Find the "Completed" list or create logic to determine target list
            completed_list = None
            for board_list in lists:
                if 'completed' in board_list['name'].lower():
                    completed_list = board_list
                    break
            
            if not completed_list:
                # If no completed list found, look for highest priority list
                # Based on your board structure, this might be "Priority 0" or similar
                priority_lists = [l for l in lists if 'priority' in l['name'].lower()]
                if priority_lists:
                    # Sort by priority number (assuming format like "Priority 0", "Priority I", etc.)
                    completed_list = priority_lists[0]  # Use first priority list as fallback
            
            if completed_list:
                # Move card to completed list
                self.trello.move_card_to_list(card['id'], completed_list['id'])
                
                # Mark as completed (close the card)
                self.trello.update_card_closed(card['id'], True)
                
                logger.info(f"Marked card '{card['name']}' in board '{board_name}' as completed")
                return True
            else:
                logger.warning(f"No suitable completed list found for card '{card['name']}' in board '{board_name}'")
                return False
                
        except Exception as e:
            logger.error(f"Error marking card '{card['name']}' in board '{board_name}' as completed: {e}")
            return False
    
    def process_board_cards(self, board_name: str):
        """Process all cards on a specific board."""
        try:
            board = self.boards[board_name]
            
            # Get all cards from the board
            cards = self.trello.get_board_cards(board['id'])
            
            logger.info(f"Processing {len(cards)} cards in board '{board_name}'...")
            
            for card in cards:
                self.stats['cards_processed'] += 1
                
                # Skip already closed cards
                if card.get('closed', False):
                    continue
                
                # Check if card has completed tag
                if self.has_completed_tag(card):
                    if self.mark_card_completed(card, board_name):
                        self.stats['cards_marked_completed'] += 1
                    else:
                        self.stats['errors'] += 1
                    continue
                
                # Check if card is overdue by 3+ days
                due_date = card.get('due')
                if due_date and self.is_overdue_by_days(due_date):
                    if self.move_card_to_monday(card, board_name):
                        self.stats['cards_moved_to_monday'] += 1
                    else:
                        self.stats['errors'] += 1
                        
        except Exception as e:
            logger.error(f"Error processing cards in board '{board_name}': {e}")
            self.stats['errors'] += 1
    
    def run(self):
        """Run the card auto-management process."""
        logger.info("Starting card auto-management...")
        
        if not self.get_boards():
            logger.error("Failed to get boards. Exiting.")
            return False
        
        # Process each board
        for board_name in self.boards.keys():
            logger.info(f"\n--- Processing board: {board_name} ---")
            self.process_board_cards(board_name)
            self.stats['boards_processed'] += 1
        
        # Log summary
        logger.info("\n=== Card auto-management completed! ===")
        logger.info(f"Summary:")
        logger.info(f"  Boards processed: {self.stats['boards_processed']}")
        logger.info(f"  Total cards processed: {self.stats['cards_processed']}")
        logger.info(f"  Cards moved to Monday: {self.stats['cards_moved_to_monday']}")
        logger.info(f"  Cards marked completed: {self.stats['cards_marked_completed']}")
        logger.info(f"  Errors: {self.stats['errors']}")
        
        return self.stats['errors'] == 0

def main():
    """Main function."""
    # Get credentials from environment variables
    api_key = os.getenv('TRELLO_API_KEY')
    token = os.getenv('TRELLO_TOKEN')
    dry_run = os.getenv('DRY_RUN', 'false').lower() == 'true'
    
    # Allow custom board names via environment variable
    board_names_env = os.getenv('TRELLO_BOARD_NAMES', 'Papers,Proposals')
    board_names = [name.strip() for name in board_names_env.split(',')]
    
    if not api_key or not token:
        logger.error("Missing required environment variables: TRELLO_API_KEY and TRELLO_TOKEN")
        sys.exit(1)
    
    # Create and run the auto-manager
    manager = CardAutoManager(api_key, token, board_names=board_names, dry_run=dry_run)
    
    try:
        success = manager.run()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
