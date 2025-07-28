import os
import json
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import datetime
from typing import Optional, Dict, Any, List
from collections import defaultdict

class TrelloMonitor:
    def __init__(self):
        # Trello API credentials from GitHub secrets
        self.api_key = os.environ['TRELLO_API_KEY']
        self.token = os.environ['TRELLO_TOKEN']
        
        # Support multiple boards - can be comma-separated list
        board_ids_str = os.environ['TRELLO_BOARD_IDS']
        self.board_ids = [bid.strip() for bid in board_ids_str.split(',')]
        
        self.base_url = 'https://api.trello.com/1'
        
        # Email configuration from GitHub secrets with robust fallbacks
        raw_smtp_host = os.environ.get('SMTP_HOST', '').strip()
        raw_smtp_port = os.environ.get('SMTP_PORT', '').strip()
        
        # Handle the case where GitHub Actions masks the values as '***'
        if not raw_smtp_host or raw_smtp_host == '***' or raw_smtp_host.startswith('.'):
            self.smtp_host = 'smtp.gmail.com'
            print("Using default SMTP host: smtp.gmail.com (GitHub secret may be masked)")
        else:
            self.smtp_host = raw_smtp_host
            
        if not raw_smtp_port or raw_smtp_port == '***':
            self.smtp_port = 587
            print("Using default SMTP port: 587 (GitHub secret may be masked)")
        else:
            try:
                self.smtp_port = int(raw_smtp_port)
            except ValueError:
                self.smtp_port = 587
                print("Invalid SMTP port, using default: 587")
        
        self.email_user = os.environ.get('EMAIL_USER', '').strip()
        self.email_pass = os.environ.get('EMAIL_PASS', '').strip()
        self.from_email = os.environ.get('FROM_EMAIL', '').strip() or self.email_user
        
        # Exemption label configuration
        self.exempt_label = os.environ.get('EXEMPT_LABEL', 'EXEMPT').strip()
        
        # Debug email configuration (without sensitive data)
        print(f"Email configuration loaded:")
        print(f"  SMTP Host: {self.smtp_host}")
        print(f"  SMTP Port: {self.smtp_port}")
        print(f"  Email User: {self.email_user[:3]}***@{self.email_user.split('@')[-1] if '@' in self.email_user else 'unknown'}")
        print(f"  From Email: {self.from_email[:3]}***@{self.from_email.split('@')[-1] if '@' in self.from_email else 'unknown'}")
        print(f"  Email Pass: {'***set***' if self.email_pass else '***NOT SET***'}")
        print(f"  Exempt Label: '{self.exempt_label}'")
        
        # Validate email configuration
        if not self.email_user or not self.email_pass:
            print("WARNING: Email credentials not properly configured!")
            print("Make sure EMAIL_USER and EMAIL_PASS secrets are set in GitHub")
        
        # State file to track changes
        self.state_file = 'trello_state.json'
        
        # Label to email mapping
        self.label_to_emails = self.load_label_email_mapping()
        
        # Flag to track if this is the first run
        self.is_first_run = False
        
        # Rate limiting settings
        self.api_calls_made = 0
        self.last_api_call_time = 0
        self.min_delay_between_calls = 0.1  # 100ms between calls
        self.rate_limit_delay = 2.0  # 2 seconds when we hit rate limit
        self.max_retries = 3

    def load_label_email_mapping(self):
        """
        Load mapping of label names to email addresses
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

    def is_card_exempt(self, card):
        """Check if a card has the exempt label"""
        label_names = {label['name'].upper() for label in card['labels']}
        is_exempt = self.exempt_label.upper() in label_names
        if is_exempt:
            print(f"Card '{card['name']}' is exempt from notifications (has '{self.exempt_label}' label)")
        return is_exempt

    def make_trello_request(self, endpoint, params=None, retries=0):
        """Make authenticated request to Trello API with rate limiting"""
        if params is None:
            params = {}
        
        # Rate limiting: ensure minimum delay between API calls
        current_time = time.time()
        time_since_last_call = current_time - self.last_api_call_time
        if time_since_last_call < self.min_delay_between_calls:
            sleep_time = self.min_delay_between_calls - time_since_last_call
            time.sleep(sleep_time)
        
        params.update({
            'key': self.api_key,
            'token': self.token
        })
        
        url = f"{self.base_url}/{endpoint}"
        
        try:
            self.last_api_call_time = time.time()
            self.api_calls_made += 1
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 429:  # Rate limit exceeded
                if retries < self.max_retries:
                    wait_time = self.rate_limit_delay * (2 ** retries)  # Exponential backoff
                    print(f"Rate limit hit. Waiting {wait_time} seconds before retry {retries + 1}/{self.max_retries}")
                    time.sleep(wait_time)
                    return self.make_trello_request(endpoint, params, retries + 1)
                else:
                    print(f"Max retries exceeded for endpoint: {endpoint}")
                    raise Exception(f"Rate limit exceeded after {self.max_retries} retries")
            
            if response.status_code != 200:
                raise Exception(f"Trello API error: {response.status_code} - {response.text}")
            
            return response.json()
            
        except requests.exceptions.Timeout:
            if retries < self.max_retries:
                print(f"Request timeout. Retrying {retries + 1}/{self.max_retries}")
                time.sleep(1)
                return self.make_trello_request(endpoint, params, retries + 1)
            else:
                raise Exception(f"Request timeout after {self.max_retries} retries")
        except requests.exceptions.RequestException as e:
            if retries < self.max_retries:
                print(f"Request error: {e}. Retrying {retries + 1}/{self.max_retries}")
                time.sleep(1)
                return self.make_trello_request(endpoint, params, retries + 1)
            else:
                raise Exception(f"Request failed after {self.max_retries} retries: {e}")

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
        print(f"Rate limiting: {self.min_delay_between_calls}s between calls, {self.rate_limit_delay}s on rate limit")
        
        all_processed_cards = {}
        
        for board_id in self.board_ids:
            print(f"Processing board: {board_id}")
            board_name = self.get_board_name(board_id)
            print(f"Board name: {board_name}")
            
            try:
                # Get all cards with detailed information for this board
                # Use a more efficient single call to get cards with all needed data
                cards_data = self.make_trello_request(
                    f'boards/{board_id}/cards',
                    {
                        'fields': 'all',
                        'members': 'true',
                        'member_fields': 'fullName,username',
                        'labels': 'true',
                        # Note: We'll fetch comments, checklists, and attachments separately
                        # to avoid overwhelming the single request
                    }
                )
                
                # Get lists to map list IDs to names for this board
                lists_data = self.make_trello_request(
                    f'boards/{board_id}/lists',
                    {'fields': 'name'}
                )
                
                list_map = {lst['id']: lst['name'] for lst in lists_data}
                
                print(f"Found {len(cards_data)} cards in board {board_name}")
                
                # Process each card in this board
                for i, card in enumerate(cards_data):
                    card_id = card['id']
                    print(f"Processing card {i+1}/{len(cards_data)}: {card['name']} (API calls made: {self.api_calls_made})")
                    
                    # Get additional card data with rate limiting
                    comments = self.get_card_comments(card_id)
                    checklists = self.get_card_checklists(card_id)
                    attachments = self.get_card_attachments(card_id)
                    
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
                        'comments': comments,
                        'checklists': checklists,
                        'attachments': attachments
                    }
                    
                    # Add a small delay between cards to be extra cautious
                    time.sleep(0.05)
                    
            except Exception as e:
                print(f"Error processing board {board_id} ({board_name}): {e}")
                continue
        
        print(f"Completed fetching all cards. Total API calls made: {self.api_calls_made}")
        return all_processed_cards

    def get_card_comments(self, card_id):
        """Get all comments for a specific card with error handling"""
        try:
            comments_data = self.make_trello_request(
                f'cards/{card_id}/actions',
                {
                    'filter': 'commentCard',
                    'fields': 'data,date,memberCreator',
                    'member_fields': 'fullName,username',
                    'limit': '50'  # Limit to reduce API load
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
            return []  # Return empty list on error instead of failing

    def get_card_checklists(self, card_id):
        """Get all checklists for a specific card with error handling"""
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
            return []  # Return empty list on error instead of failing

    def get_card_attachments(self, card_id):
        """Get all attachments for a specific card with error handling"""
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
            return []  # Return empty list on error instead of failing

    def load_previous_state(self):
        """Load the previous state from file"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state_data = json.load(f)
                    print(f"Loaded previous state with {len(state_data.get('cards', {}))} cards")
                    return state_data.get('cards', {})
            else:
                print("State file does not exist, this is the first run")
                self.is_first_run = True
                return {}
        except json.JSONDecodeError as e:
            print(f"Error reading state file (corrupted JSON): {e}")
            print("Starting fresh with empty state")
            self.is_first_run = True
            return {}
        except Exception as e:
            print(f"Error loading state file: {e}")
            print("Starting fresh with empty state")
            self.is_first_run = True
            return {}

    def save_current_state(self, cards_state):
        """Save the current state to file with metadata"""
        def default_serializer(obj):
            if isinstance(obj, datetime.datetime):
                return obj.isoformat()
            return str(obj)
    
        try:
            state_data = {
                'last_updated': datetime.datetime.now().isoformat(),
                'total_cards': len(cards_state),
                'boards_monitored': self.board_ids,
                'cards': cards_state
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(state_data, f, indent=2, default=default_serializer)
            print(f"State saved successfully with {len(cards_state)} cards")
        except Exception as e:
            print(f"Error saving state: {e}")
            raise

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
            old_due = datetime.datetime.fromisoformat(old_card['due'].replace('Z', '+00:00')).strftime('%Y-%m-%d') if old_card['due'] else 'None'
            new_due = datetime.datetime.fromisoformat(new_card['due'].replace('Z', '+00:00')).strftime('%Y-%m-%d') if new_card['due'] else 'None'
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
        
        return list(emails)

    def send_bulk_notification_email(self, recipient_email: str, card_changes: List[Dict]):
        """Send a bulk email notification with all card changes for a specific recipient"""
        if not card_changes:
            return
            
        # Check if email is configured
        if not self.email_user or not self.email_pass:
            print("Email not configured - skipping notification")
            return

        try:
            # Create subject line
            card_count = len(card_changes)
            total_changes = sum(len(card_data['changes']) for card_data in card_changes)
            subject = f"Trello Updates: {total_changes} changes across {card_count} card{'s' if card_count > 1 else ''}"
            
            # Create HTML body
            body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 800px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #0079bf; border-bottom: 2px solid #0079bf; padding-bottom: 10px;">
                        📋 Trello Updates Summary
                    </h2>
                    
                    <div style="background-color: #f4f5f7; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
                        <strong>Summary:</strong> {total_changes} changes detected across {card_count} card{'s' if card_count > 1 else ''}
                        <br><strong>Generated:</strong> {datetime.datetime.now().strftime('%Y-%m-%d at %H:%M:%S')}
                    </div>
            """
            
            # Group cards by board for better organization
            boards = defaultdict(list)
            for card_data in card_changes:
                card = card_data['card']
                boards[card['board_name']].append(card_data)
            
            # Add cards organized by board
            for board_name, board_cards in boards.items():
                body += f"""
                    <h3 style="color: #0079bf; margin-top: 30px; margin-bottom: 15px;">
                        📌 Board: {board_name}
                    </h3>
                """
                
                for card_data in board_cards:
                    card = card_data['card']
                    changes = card_data['changes']
                    
                    # Card header
                    body += f"""
                        <div style="border: 1px solid #ddd; border-radius: 8px; margin-bottom: 20px; overflow: hidden;">
                            <div style="background-color: #0079bf; color: white; padding: 12px; font-weight: bold;">
                                🗂️ {card['name']}
                            </div>
                            <div style="padding: 15px;">
                                <div style="margin-bottom: 10px;">
                                    <strong>List:</strong> {card['list_name']} | 
                                    <strong>Last Activity:</strong> {card['date_last_activity'][:10]}
                                </div>
                    """
                    
                    # Add labels if any
                    if card['labels']:
                        labels_html = ' '.join([
                            f"<span style='background-color: #{label.get('color', 'gray')}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 12px; margin-right: 5px;'>{label['name']}</span>"
                            for label in card['labels'] if label['name']
                        ])
                        body += f"<div style='margin-bottom: 10px;'><strong>Labels:</strong> {labels_html}</div>"
                    
                    # Add description preview if exists
                    if card['desc']:
                        desc_preview = card['desc'][:150] + ('...' if len(card['desc']) > 150 else '')
                        body += f"<div style='margin-bottom: 15px; font-style: italic; color: #666;'>Description: {desc_preview}</div>"
                    
                    # Add changes
                    body += f"""
                                <h4 style="color: #d04437; margin-bottom: 8px;">
                                    ⚡ Changes ({len(changes)}):
                                </h4>
                                <ul style="margin: 0; padding-left: 20px;">
                    """
                    
                    for change in changes:
                        # Add emoji based on change type
                        emoji = {
                            'card_created': '✨',
                            'name_changed': '📝',
                            'description_changed': '📄',
                            'moved': '↔️',
                            'moved_between_boards': '🔄',
                            'due_date_changed': '📅',
                            'comment_added': '💬',
                            'label_added': '🏷️',
                            'label_removed': '🏷️',
                            'checklist_changed': '✅',
                            'attachment_added': '📎'
                        }.get(change['type'], '•')
                        
                        body += f"<li style='margin-bottom: 5px;'>{emoji} {change['description']}</li>"
                    
                    body += """
                                </ul>
                            </div>
                        </div>
                    """
            
            # Footer
            body += f"""
                    <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                    <div style="text-align: center; color: #666; font-size: 12px;">
                        <p>🤖 This is an automated notification from your Trello monitoring system.</p>
                        <p>You're receiving this because you're subscribed to updates for cards with specific labels.</p>
                    </div>
                </div>
            </body>
            </html>
            """

            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = recipient_email

            # Add HTML body
            html_part = MIMEText(body, 'html')
            msg.attach(html_part)

            # Send email with proper connection handling
            print(f"Attempting to send bulk email to: {recipient_email}")
            print(f"Using SMTP server: {self.smtp_host}:{self.smtp_port}")
            
            # Create SMTP connection
            server = None
            try:
                print("Creating SMTP connection...")
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
                
                print("Starting TLS...")
                server.starttls()
                print("TLS started successfully")
                
                print("Logging in...")
                server.login(self.email_user, self.email_pass)
                print("SMTP login successful")
                
                print("Sending message...")
                server.send_message(msg)
                print(f"Bulk email sent successfully to: {recipient_email} (contained {total_changes} changes across {card_count} cards)")
                
            except smtplib.SMTPAuthenticationError as e:
                print(f"SMTP Authentication failed: {e}")
                print("Please check your EMAIL_USER and EMAIL_PASS credentials")
                print("For Gmail, make sure you're using an App Password, not your regular password")
                
            except smtplib.SMTPRecipientsRefused as e:
                print(f"Recipients refused: {e}")
                print("Please check the recipient email addresses")
                
            except smtplib.SMTPServerDisconnected as e:
                print(f"SMTP server disconnected: {e}")
                print("Connection to SMTP server was lost")
                
            except smtplib.SMTPConnectError as e:
                print(f"SMTP connection error: {e}")
                print("Could not connect to SMTP server")
                
            except Exception as e:
                print(f"Error during email sending: {e}")
                import traceback
                traceback.print_exc()
                
            finally:
                if server:
                    try:
                        server.quit()
                        print("SMTP connection closed")
                    except:
                        pass

        except Exception as e:
            print(f"Error creating bulk email: {e}")
            import traceback
            traceback.print_exc()

    def run_monitoring_cycle(self):
        """Run one complete monitoring cycle with bulk email notifications"""
        print(f"Starting monitoring cycle at {datetime.datetime.now()}")
        
        try:
            # Load previous state
            previous_state = self.load_previous_state()
            
            # Fetch current state
            current_state = self.fetch_all_cards()
            
            if self.is_first_run:
                print("This is the first run - initializing state file")
                print(f"Found {len(current_state)} cards across {len(self.board_ids)} boards")
                print("No change detection will be performed on this run")
                # Save the initial state and exit
                self.save_current_state(current_state)
                print("Initial state saved. Future runs will detect changes.")
                return
            
            # Compare states and detect changes
            changes_detected = 0
            exempt_cards_skipped = 0
            
            # Group changes by recipient email for bulk notifications
            email_to_changes = defaultdict(list)
            
            for card_id, current_card in current_state.items():
                # Skip exempt cards
                if self.is_card_exempt(current_card):
                    exempt_cards_skipped += 1
                    continue
                
                previous_card = previous_state.get(card_id)
                changes = self.compare_cards(previous_card, current_card)
                
                if changes:
                    changes_detected += 1
                    print(f"Changes detected for card: {current_card['name']}")
                    for change in changes:
                        print(f"  - {change['description']}")
                    
                    # Get email addresses for this card
                    emails = self.get_emails_for_card(current_card)
                    
                    # Group changes by recipient email
                    for email in emails:
                        email_to_changes[email].append({
                            'card': current_card,
                            'changes': changes
                        })

            # Send bulk notification emails
            notifications_sent = 0
            for recipient_email, card_changes in email_to_changes.items():
                self.send_bulk_notification_email(recipient_email, card_changes)
                notifications_sent += 1

            # Check for deleted cards
            deleted_cards = 0
            for card_id in previous_state:
                if card_id not in current_state:
                    deleted_card = previous_state[card_id]
                    deleted_cards += 1
                    print(f"Card deleted: {deleted_card['name']} from board {deleted_card['board_name']}")
                    # You could send deletion notifications here too if needed

            # Save current state for next run
            self.save_current_state(current_state)
            
            # Print summary
            print(f"\nMonitoring cycle completed at {datetime.datetime.now()}")
            print(f"Summary:")
            print(f"  - Total cards monitored: {len(current_state)}")
            print(f"  - Cards with changes: {changes_detected}")
            print(f"  - Cards skipped (exempt): {exempt_cards_skipped}")
            print(f"  - Bulk notifications sent: {notifications_sent}")
            print(f"  - Cards deleted: {deleted_cards}")
            print(f"  - Exempt label: '{self.exempt_label}'")
            
        except Exception as e:
            print(f"Error during monitoring cycle: {e}")
            raise

def main():
    """Main function to run the Trello monitor"""
    monitor = TrelloMonitor()
    monitor.run_monitoring_cycle()

if __name__ == "__main__":
    main()
