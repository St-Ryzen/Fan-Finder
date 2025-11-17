import os
import json
from datetime import datetime
import sys

# Add the project root to the path to import the license manager
project_root = os.path.join(os.path.dirname(__file__), '..', '..')
if project_root not in sys.path:
    sys.path.insert(0, os.path.abspath(project_root))

# Import LicenseManager with error handling
try:
    from app.backend.license_manager import LicenseManager
except ImportError:
    # If the above fails, try alternative import method
    backend_path = os.path.join(os.path.dirname(__file__), '..', 'backend')
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    from license_manager import LicenseManager

try:
    from pyairtable import Api
    PYAIRTABLE_AVAILABLE = True
except ImportError:
    print("[WARNING] pyairtable library not available. Install it with 'pip install pyairtable'")
    PYAIRTABLE_AVAILABLE = False
    Api = None


class AirTableHandler:
    def __init__(self):
        """Initialize the AirTable handler by fetching configuration from Supabase"""
        if not PYAIRTABLE_AVAILABLE:
            print("[INFO] pyairtable library is not available - AirTable sync disabled")
            self.api_key = None
            self.base_id = None
            self.table_id = None
            self.username_field = None
            self.total_fans_field = None
            self.last_updated_field = None
            self.airtable_api = None
            self.table = None
        else:
            self.license_manager = LicenseManager()
            self.airtable_config = self._get_airtable_config()
            
            if self.airtable_config:
                self.api_key = self.airtable_config.get('api_key')
                self.base_id = self.airtable_config.get('base_id')
                self.table_id = self.airtable_config.get('table_id')
                self.username_field = self.airtable_config.get('username_field')
                self.total_fans_field = self.airtable_config.get('total_fans_field')
                self.last_updated_field = self.airtable_config.get('last_updated_field')
                
                # Initialize the AirTable API
                self.airtable_api = Api(self.api_key)
                self.table = self.airtable_api.table(self.base_id, self.table_id)
            else:
                print("[ERROR] Could not retrieve AirTable configuration from Supabase")
                self.api_key = None
                self.base_id = None
                self.table_id = None
                self.username_field = None
                self.total_fans_field = None
                self.last_updated_field = None
                self.airtable_api = None
                self.table = None
    
    def update_supabase_user_data(self, email, total_count, last_updated=None):
        """
        Update Supabase record for a specific user (similar to AirTable update function)
        This allows for real-time updates like AirTable
        """
        try:
            if not self.license_manager or not self.license_manager.supabase:
                print("[ERROR] License manager or Supabase client not initialized")
                return False
            
            if last_updated is None:
                last_updated = datetime.now().isoformat()
            
            # Prepare the update data (only update count and timestamps, not the full user list)
            # This allows for real-time count updates without replacing the full user list
            update_data = {
                'total_count': total_count,
                'last_updated': last_updated,
                'updated_at': datetime.now().isoformat()
            }
            
            # Update the existing record
            result = self.license_manager.supabase.table('collected_users').update(update_data).eq('email', email).execute()
            
            # Check if any rows were affected
            if hasattr(result, 'count') and result.count == 0 or (hasattr(result, 'data') and result.data is not None and len(result.data) == 0):
                print(f"[INFO] No existing record found for {email}, will insert new record")
                # If no record was updated, insert a new one
                full_record = {
                    'email': email,
                    'users': [],  # Empty initially, will be filled by sync_users_to_supabase
                    'total_count': total_count,
                    'last_updated': last_updated,
                    'updated_at': datetime.now().isoformat()
                }
                self.license_manager.supabase.table('collected_users').upsert(
                    full_record, 
                    on_conflict='email'
                ).execute()
                print(f"[SUCCESS] Inserted new Supabase record for {email}, total_count: {total_count}")
            else:
                print(f"[SUCCESS] Updated Supabase record for {email}, total_count: {total_count}")
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to update Supabase user data: {e}")
            return False
    
    def sync_users_to_supabase(self, email, users_set):
        """
        Sync user data to Supabase for centralized storage and team synchronization
        """
        try:
            if not self.license_manager or not self.license_manager.supabase:
                print("[ERROR] License manager or Supabase client not initialized")
                return False
            
            # Prepare the user data to store
            user_data = {
                'email': email,
                'users': list(users_set),
                'total_count': len(users_set),
                'last_updated': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            # Use upsert with on_conflict parameter to handle the unique email constraint
            result = self.license_manager.supabase.table('collected_users').upsert(
                user_data, 
                on_conflict='email'
            ).execute()
            
            print(f"[SUCCESS] Synced {len(users_set)} users for {email} to Supabase")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to sync users to Supabase: {e}")
            return False
    
    def get_users_from_supabase(self, email):
        """
        Retrieve user data from Supabase for a specific user
        """
        try:
            if not self.license_manager or not self.license_manager.supabase:
                print("[ERROR] License manager or Supabase client not initialized")
                return set()
            
            # Get user data from Supabase
            result = self.license_manager.supabase.table('collected_users').select('users').eq('email', email).execute()
            
            if result.data:
                # Extract users from the first record
                user_data = result.data[0]
                users_list = user_data.get('users', [])
                users_set = set(users_list) if users_list else set()
                
                print(f"[SUCCESS] Loaded {len(users_set)} users from Supabase for {email}")
                return users_set
            else:
                print(f"[INFO] No existing user data found in Supabase for {email}")
                return set()
                
        except Exception as e:
            print(f"[ERROR] Failed to get users from Supabase: {e}")
            return set()
    
    def merge_users_from_supabase(self, email, current_users_set):
        """
        Merge existing local users with users from Supabase, with Supabase as authoritative source
        """
        try:
            supabase_users = self.get_users_from_supabase(email)
            # Combine all unique users, with Supabase as the authoritative source
            all_users = current_users_set.union(supabase_users)
            
            print(f"[INFO] Merged local data ({len(current_users_set)} users) with Supabase data ({len(supabase_users)} users), total: {len(all_users)} users")
            return all_users
        except Exception as e:
            print(f"[ERROR] Failed to merge users from Supabase: {e}")
            return current_users_set
    
    def _get_airtable_config(self):
        """Fetch AirTable configuration from Supabase"""
        try:
            if not self.license_manager or not self.license_manager.supabase:
                print("[ERROR] License manager or Supabase client not initialized")
                return None
            
            # Get AirTable configuration from Supabase
            response = self.license_manager.supabase.table('config').select('*').eq('id', 'airtable_config').execute()
            
            if response.data:
                config_data = response.data[0]
                # If the config is stored in a 'data' field
                if isinstance(config_data, dict) and 'data' in config_data:
                    return config_data['data']
                # If the config is stored directly
                elif isinstance(config_data, dict):
                    return config_data
                else:
                    print(f"[ERROR] Unexpected configuration format: {config_data}")
                    return None
            else:
                print("[ERROR] AirTable configuration not found in Supabase")
                return None
        
        except Exception as e:
            print(f"[ERROR] Failed to get AirTable configuration from Supabase: {e}")
            return None
    
    def update_user_data(self, username, total_count, last_updated):
        """Update the AirTable record for a specific username"""
        if not PYAIRTABLE_AVAILABLE:
            print("[ERROR] pyairtable library is not available")
            return False
            
        if not self.table:
            print("[ERROR] AirTable connection not initialized")
            return False
        
        try:
            # Convert date string to datetime object if needed
            if isinstance(last_updated, str):
                # Parse the date string to datetime object
                last_updated = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
            
            # Format date for AirTable (ISO format)
            formatted_date = last_updated.isoformat()
            
            # Query AirTable for the record matching the username
            filter_formula = f'{{{self.username_field}}}="{username}"'
            records = self.table.all(formula=filter_formula)
            
            # Prepare the update data
            update_data = {
                self.total_fans_field: total_count,
                self.last_updated_field: formatted_date
            }
            
            if records:
                # Update the existing record
                record_id = records[0]['id']
                self.table.update(record_id, update_data)
                print(f"[SUCCESS] Updated AirTable record for username: {username}")
                return True
            else:
                print(f"[INFO] No existing record found for username: {username}")
                # Optionally create a new record if it doesn't exist
                return False
        
        except Exception as e:
            print(f"[ERROR] Failed to update AirTable record for username {username}: {e}")
            return False
    
    def update_from_json_file(self, json_file_path):
        """Update AirTable with data from a JSON file"""
        if not PYAIRTABLE_AVAILABLE:
            print("[ERROR] pyairtable library is not available")
            return False
        
        if not os.path.exists(json_file_path):
            print(f"[ERROR] JSON file does not exist: {json_file_path}")
            return False
        
        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            username = data.get('owner_email', data.get('username'))
            total_count = data.get('total_count', 0)
            last_updated = data.get('last_updated')
            
            if not username:
                print("[ERROR] Username not found in JSON file")
                return False
            
            if not last_updated:
                # Use current time if not provided
                last_updated = datetime.now().isoformat()
            
            return self.update_user_data(username, total_count, last_updated)
        
        except Exception as e:
            print(f"[ERROR] Failed to read and process JSON file {json_file_path}: {e}")
            return False