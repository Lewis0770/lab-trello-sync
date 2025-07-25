import os
import json
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import time

class TrelloMonitor:
    def __init__(self):
        # Trello API credentials from GitHub secrets
        self.api_key = os.environ['TRELLO_API_KEY']
        self.token = os.environ['TRELLO_TOKEN']
        
        # Support multiple boards - can be comma-separated list
        board_ids_str = os.environ['TRELLO_BOARD_IDS']
        self.board_ids = [bid.strip() for bid in board_ids_str.split(',')]
        
        self.base_url = 'https://api.trello.com/1'
        
        # Email configuration from GitHub secrets
        self.smtp_host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        self.email_user = os.environ['EMAIL_USER']
        self.email_pass = os.environ['EMAIL_PASS']
        self.from_email = os.environ.get('FROM_EMAIL', self.email_user)
        
        # State file to track changes
        self.state_file = 'trello_state.json'
        
        # Label to email mapping (you'll need to set this up)
        self.label_to_emails = self.load_label_email_mapping()

    def load_label_email_mapping(self):
        """
        Load mapping of label names to email addresses
        You can either hardcode this or load from environment variables
        """
        # Option 1: From environment variable (JSON string)
        if 'LABEL_EMAIL_MAPPING' in os.environ:
            return json.loads(os.environ['LABEL_EMAIL_MAPPING'])
        
        # Option 2: Default mapping (customize as needed)
        return {
            'Brandon': ['brandonlewis0405@gmail.com'],
            'Jane Smith': ['jane.smith@example.com'],
            'Team Lead': ['lead@example.com'],
            'Developer': ['dev@example.com']
        }

    def make_trello_request(self, endpoint, params=None):
        """Make authenticated request to Trello API"""
        if params is None:
            params = {}
        
        params.update({
            'key': self.api_key,
            'token': self.token
        })
        
        url = f"{self.base_url}/{endpoint}"
        response = requests.get(url, params=params)
        
        if response.status_code != 200:
            raise Exception(f"Trello API error: {response.status_code} - {response.text}")
        
        return response.json()

    def get_board_name(self, board_id):
        """Get the name of a board"""
        try:
            board_data = self.make_trello_request(f'boards/{board_id}', {'fields': 'name'})
            return board_data['name']
        except Exception as e:
            print(f"Error fetching board name for {board_id}: {e}")
            return f"Board {board_id}"

    def fetch_all_cards(self):
        """Fetch all cards from all boards with comprehensive metadata"""
        print("Fetching all cards from all Trello boards...")
        
        all_processed_cards = {}
        
        for board_id in self.board_ids:
            print(f"Processing board: {board_id}")
            board_name = self.get_board_name(board_id)
            print(f"Board name: {board_name}")
            
            try:
                # Get all cards with detailed information for this board
                cards_data = self.make_trello_request(
                    f'boards/{board_id}/cards',
                    {
                        'fields': 'all',
                        'members': 'true',
                        'member_fields': 'all',
                        'labels': 'true',
                        'actions': 'commentCard',
                        'actions_limit': '1000'
                    }
                )
                
                # Get lists to map list IDs to names for this board
                lists_data = self.make_trello_request(
                    f'boards/{board_id}/lists',
                    {'fields': 'name'}
                )
                
                list_map = {lst['id']: lst['name'] for lst in lists_data}
                
                # Process each card in this board
                for card in cards_data:
                    card_id = card['id']
                    print(f"Processing card: {card['name']} (Board: {board_name})")
                    
                    all_processed_cards[card_id] = {
                        'id': card_id,
                        'board_id': board_id,
                        'board_name': board_name,
                        'name': card['name'],
                        'desc': card['desc'],
                        'list_id': card['idList'],
                        'list_name': list_map.get(card['idList'], 'Unknown List'),
                        'pos': card['pos'],
                        'due': card['due'],
                        'due_complete': card['dueComplete'],
                        'closed': card['closed'],
                        'date_last_activity': card['dateLastActivity'],
                        'labels': [
                            {
                                'id': label['id'],
                                'name': label['name'],
                                'color': label['color']
                            }
                            for label in card['labels']
                        ],
                        'members': [
                            {
                                'id': member['id'],
                                'username': member['username'],
                                'full_name': member['fullName']
                            }
                            for member in card['members']
                        ],
                        'comments': self.get_card_comments(card_id),
                        'checklists': self.get_card_checklists(card_id),
                        'attachments': self.get_card_attachments(card_id)
                    }
                    
            except Exception as e:
                print(f"Error processing board {board_id} ({board_name}): {e}")
                continue
        
        return all_processed_cards

    def get_card_comments(self, card_id):
        """Get all comments for a specific card"""
        try:
            comments_data = self.make_trello_request(
                f'cards/{card_id}/actions',
                {
                    'filter': 'commentCard',
                    'fields': 'data,date,memberCreator',
                    'member_fields': 'fullName,username'
                }
            )
            
            return [
                {
                    'id': comment['id'],
                    'text': comment['data']['text'],
                    'date': comment['date'],
                    'author': {
                        'full_name': comment['memberCreator']['fullName'],
                        'username': comment['memberCreator']['username']
                    } if comment.get('memberCreator') else None
                }
                for comment in comments_data
            ]
        except Exception as e:
            print(f"Error fetching comments for card {card_id}: {e}")
            return []

    def get_card_checklists(self, card_id):
        """Get all checklists for a specific card"""
        try:
            checklists_data = self.make_trello_request(
                f'cards/{card_id}/checklists',
                {
                    'fields': 'name,pos',
                    'checkItems': 'all',
                    'checkItem_fields': 'name,state,pos'
                }
            )
            
            return [
                {
                    'id': checklist['id'],
                    'name': checklist['name'],
                    'pos': checklist['pos'],
                    'items': [
                        {
                            'id': item['id'],
                            'name': item['name'],
                            'state': item['state'],
                            'pos': item['pos']
                        }
                        for item in checklist.get('checkItems', [])
                    ]
                }
                for checklist in checklists_data
            ]
        except Exception as e:
            print(f"Error fetching checklists for card {card_id}: {e}")
            return []

    def get_card_attachments(self, card_id):
        """Get all attachments for a specific card"""
        try:
            attachments_data = self.make_trello_request(
                f'cards/{card_id}/attachments',
                {'fields': 'name,url,date'}
            )
            
            return [
                {
                    'id': attachment['id'],
                    'name': attachment['name'],
                    'url': attachment['url'],
                    'date': attachment['date']
                }
                for attachment in attachments_data
            ]
        except Exception as e:
            print(f"Error fetching attachments for card {card_id}: {e}")
            return []

    def load_previous_state(self):
        """Load the previous state from file"""
        try:
            with open(self.state_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print("No previous state found, starting fresh")
            return {}
        except json.JSONDecodeError:
            print("Error reading state file, starting fresh")
            return {}

    def save_current_state(self, state):
        """Save current state to file"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            print("State saved successfully")
        except Exception as e:
            print(f"Error saving state: {e}")

    def compare_cards(self, old_card, new_card):
        """Compare two card states and detect changes"""
        changes = []
        
        if old_card is None:
            changes.append({
                'type': 'card_created',
                'description': f'Card "{new_card["name"]}" was created in list "{new_card["list_name"]}" on board "{new_card["board_name"]}"'
            })
            return changes

        # Check basic properties
        if old_card['name'] != new_card['name']:
            changes.append({
                'type': 'name_changed',
                'description': f'Card name changed from "{old_card["name"]}" to "{new_card["name"]}"'
            })

        if old_card['desc'] != new_card['desc']:
            changes.append({
                'type': 'description_changed',
                'description': 'Card description was updated'
            })

        if old_card['list_name'] != new_card['list_name']:
            # Check if it's a move within the same board or between boards
            if old_card.get('board_name') != new_card.get('board_name'):
                changes.append({
                    'type': 'moved_between_boards',
                    'description': f'Card moved from "{old_card["list_name"]}" on board "{old_card.get("board_name", "Unknown")}" to "{new_card["list_name"]}" on board "{new_card["board_name"]}"'
                })
            else:
                changes.append({
                    'type': 'moved',
                    'description': f'Card moved from "{old_card["list_name"]}" to "{new_card["list_name"]}" on board "{new_card["board_name"]}"'
                })
        elif old_card.get('board_name') != new_card.get('board_name'):
            # Same list name but different board (rare case)
            changes.append({
                'type': 'moved_between_boards',
                'description': f'Card moved from board "{old_card.get("board_name", "Unknown")}" to board "{new_card["board_name"]}"'
            })

        if old_card['due'] != new_card['due']:
            old_due = datetime.fromisoformat(old_card['due'].replace('Z', '+00:00')).strftime('%Y-%m-%d') if old_card['due'] else 'None'
            new_due = datetime.fromisoformat(new_card['due'].replace('Z', '+00:00')).strftime('%Y-%m-%d') if new_card['due'] else 'None'
            changes.append({
                'type': 'due_date_changed',
                'description': f'Due date changed from {old_due} to {new_due}'
            })

        # Check comments
        if len(new_card['comments']) > len(old_card['comments']):
            new_comments_count = len(new_card['comments']) - len(old_card['comments'])
            for i in range(new_comments_count):
                comment = new_card['comments'][i]
                author_name = comment['author']['full_name'] if comment['author'] else 'Unknown'
                comment_preview = comment['text'][:100] + ('...' if len(comment['text']) > 100 else '')
                changes.append({
                    'type': 'comment_added',
                    'description': f'New comment by {author_name}: "{comment_preview}"'
                })

        # Check labels
        old_label_names = {label['name'] for label in old_card['labels']}
        new_label_names = {label['name'] for label in new_card['labels']}
        
        added_labels = new_label_names - old_label_names
        removed_labels = old_label_names - new_label_names
        
        for label in added_labels:
            changes.append({
                'type': 'label_added',
                'description': f'Label "{label}" was added'
            })
        
        for label in removed_labels:
            changes.append({
                'type': 'label_removed',
                'description': f'Label "{label}" was removed'
            })

        # Check checklists
        old_checklist_items = sum(len(cl['items']) for cl in old_card['checklists'])
        new_checklist_items = sum(len(cl['items']) for cl in new_card['checklists'])
        
        if new_checklist_items != old_checklist_items:
            changes.append({
                'type': 'checklist_changed',
                'description': f'Checklist items changed (was {old_checklist_items}, now {new_checklist_items})'
            })

        # Check attachments
        if len(new_card['attachments']) > len(old_card['attachments']):
            new_attachments_count = len(new_card['attachments']) - len(old_card['attachments'])
            changes.append({
                'type': 'attachment_added',
                'description': f'{new_attachments_count} new attachment(s) added'
            })

        return changes

    def get_emails_for_card(self, card):
        """Get email addresses for users who should be notified about this card"""
        emails = set()
        
        # Get emails based on labels
        for label in card['labels']:
            label_name = label['name']
            if label_name in self.label_to_emails:
                emails.update(self.label_to_emails[label_name])
        
        # If no label-based emails found, you might want to use card members
        # (though Trello API doesn't always provide member emails)
        
        return list(emails)

    def send_notification_email(self, emails, card, changes):
        """Send email notification about card changes"""
        if not emails:
            print(f"No email addresses found for card: {card['name']}")
            return

        try:
            # Create email content
            subject = f"Trello Card Update: {card['name']}"
            
            body = f"""
            <html>
            <body>
                <h2>Card Update Notification</h2>
                <p><strong>Card:</strong> {card['name']}</p>
                <p><strong>Board:</strong> {card['board_name']}</p>
                <p><strong>List:</strong> {card['list_name']}</p>
                <p><strong>Last Activity:</strong> {card['date_last_activity']}</p>
                
                <h3>Changes Detected:</h3>
                <ul>
            """
            
            for change in changes:
                body += f"<li>{change['description']}</li>"
            
            body += f"""
                </ul>
                
                <p><strong>Card Description:</strong></p>
                <p>{card['desc'] if card['desc'] else 'No description'}</p>
                
                <p><strong>Labels:</strong> {', '.join([label['name'] for label in card['labels']]) if card['labels'] else 'None'}</p>
                
                <hr>
                <p><em>This is an automated notification from your Trello monitoring system.</em></p>
            </body>
            </html>
            """

            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = ', '.join(emails)

            # Add HTML body
            html_part = MIMEText(body, 'html')
            msg.attach(html_part)

            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_user, self.email_pass)
                server.send_message(msg)

            print(f"Email sent to: {', '.join(emails)} for card: {card['name']}")

        except Exception as e:
            print(f"Error sending email: {e}")

    def run_monitoring_cycle(self):
        """Run one complete monitoring cycle"""
        print(f"Starting monitoring cycle at {datetime.now()}")
        
        try:
            # Load previous state
            previous_state = self.load_previous_state()
            
            # Fetch current state
            current_state = self.fetch_all_cards()
            
            # Compare states and detect changes
            for card_id, current_card in current_state.items():
                previous_card = previous_state.get(card_id)
                changes = self.compare_cards(previous_card, current_card)
                
                if changes:
                    print(f"Changes detected for card: {current_card['name']}")
                    for change in changes:
                        print(f"  - {change['description']}")
                    
                    # Get email addresses for this card
                    emails = self.get_emails_for_card(current_card)
                    
                    # Send notification
                    if emails:
                        self.send_notification_email(emails, current_card, changes)
                    else:
                        print(f"No email recipients configured for card: {current_card['name']}")

            # Check for deleted cards
            for card_id in previous_state:
                if card_id not in current_state:
                    deleted_card = previous_state[card_id]
                    print(f"Card deleted: {deleted_card['name']}")
                    # You might want to send deletion notifications too

            # Save current state for next run
            self.save_current_state(current_state)
            
            print(f"Monitoring cycle completed at {datetime.now()}")
            
        except Exception as e:
            print(f"Error during monitoring cycle: {e}")
            raise

def main():
    """Main function to run the Trello monitor"""
    monitor = TrelloMonitor()
    monitor.run_monitoring_cycle()

if __name__ == "__main__":
    main()
