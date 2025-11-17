#!/usr/bin/env python3
"""
Supabase License Manager - Replaces Firebase License Manager
"""

import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client, Client
import hashlib

# Load environment variables
load_dotenv()

class LicenseManager:
    """Manage Supabase subscriptions and license validation"""
    
    def __init__(self):
        """Initialize Supabase connection"""
        self.supabase = None
        self._initialize_supabase()
    
    def _initialize_supabase(self):
        """Initialize Supabase client"""
        try:
            # Try to get Supabase configuration from environment variables first (for production security)
            SUPABASE_URL = os.getenv('SUPABASE_URL')
            SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY')
            
            # If not found in environment variables, use the application's default credentials
            if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
                # Load from secrets file (contains default application credentials)
                try:
                    secrets_file_path = os.path.join(os.path.dirname(__file__), 'config', 'secrets.json')
                    if os.path.exists(secrets_file_path):
                        with open(secrets_file_path, 'r') as f:
                            secrets_data = json.load(f)
                            if 'supabase' in secrets_data:
                                SUPABASE_URL = secrets_data['supabase'].get('url')
                                SUPABASE_SERVICE_KEY = secrets_data['supabase'].get('service_key')
                                if SUPABASE_URL and SUPABASE_SERVICE_KEY:
                                    print("[INFO] Using default application Supabase credentials")
                except Exception as e:
                    print(f"[WARNING] Could not read secrets file: {e}")
            
            # Fallback to hardcoded defaults if nothing else works (should not happen)
            if not SUPABASE_URL:
                SUPABASE_URL = "https://btncjzskkhbcmjmmztwo.supabase.co"
            if not SUPABASE_SERVICE_KEY:
                SUPABASE_SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ0bmNqenNra2hiY21qbW16dHdvIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NjcyMTUyMiwiZXhwIjoyMDcyMjk3NTIyfQ.ZRlviTcbpJhztuYYfP5_MkaqT4tTDE8M4uNwvK3T3bM"
                print("[INFO] Using hardcoded fallback credentials")
            
            # Create Supabase client with service role key
            self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
            print("[INFO] Supabase initialized successfully")
            
        except Exception as e:
            print(f"[ERROR] Supabase initialization failed: {e}")
            self.supabase = None
    
    def check_subscription(self, username):
        """Check if username has active subscription"""
        try:
            if not self.supabase:
                print("[ERROR] Supabase not initialized")
                return {'success': False, 'message': 'Supabase not initialized'}
            
            if not username or len(username.strip()) == 0:
                print("[ERROR] Invalid username provided")
                return {'success': False, 'message': 'Invalid username'}
            
            username = username.strip().lower()  # Normalize username
            print(f"[DEBUG] Checking subscription for normalized username: '{username}'")
            
            # Get subscription from Supabase
            response = self.supabase.table('subscriptions').select('*').eq('username', username).execute()
            
            if not response.data:
                print(f"[INFO] No subscription found for username: '{username}'")
                return {'success': False, 'message': 'No subscription found'}
            
            # Get subscription data
            subscription_data = response.data[0]
            print(f"[DEBUG] Subscription data found: {subscription_data}")
            
            # Check subscription status
            status = subscription_data.get('status', 'inactive')
            print(f"[DEBUG] Subscription status: '{status}'")
            
            if status != 'active':
                print(f"[INFO] Subscription status is '{status}' for username: '{username}' - access denied")
                return {'success': False, 'message': f'Subscription status: {status}'}
            
            # Get subscription tier
            tier = subscription_data.get('tier', 'basic')
            
            # Define tier limits
            tier_limits = {
                'basic': 25,      # 1 month plan
                'premium': -1,    # 6 months plan (unlimited)
                'enterprise': -1  # 1 year plan (unlimited)
            }
            
            max_fans = tier_limits.get(tier, 25)  # Default to basic limits
            
            # Check subscription expiry
            subscription_end = subscription_data.get('subscription_end')
            days_remaining = 0
            
            if subscription_end:
                print(f"[DEBUG] Subscription end date: {subscription_end}")
                
                # Parse subscription end date
                if isinstance(subscription_end, str):
                    try:
                        end_date = datetime.fromisoformat(subscription_end.replace('Z', '+00:00'))
                        end_date = end_date.replace(tzinfo=None)  # Remove timezone for comparison
                    except ValueError:
                        print(f"[ERROR] Invalid date format in subscription_end: {subscription_end}")
                        return {'success': False, 'message': 'Invalid subscription date format'}
                else:
                    end_date = subscription_end
                
                # Check if subscription has expired
                current_date = datetime.now()
                print(f"[DEBUG] Current date: {current_date}, End date: {end_date}")
                
                if current_date > end_date:
                    print(f"[INFO] Subscription expired on {end_date} for username: '{username}' - access denied")
                    # Update status to expired
                    self._update_subscription_status(username, 'expired')
                    return {'success': False, 'message': 'Subscription expired'}
                else:
                    days_remaining = (end_date - current_date).days
                    print(f"[INFO] Subscription active, {days_remaining} days remaining for username: '{username}'")
            else:
                print(f"[WARNING] No subscription_end date found for username: '{username}' - treating as invalid")
                return {'success': False, 'message': 'No subscription end date'}
            
            # Check if this is a trial subscription
            trial_used = subscription_data.get('trial_used', False)
            is_trial = subscription_data.get('is_trial', False)
            
            print(f"[SUCCESS] Active subscription confirmed for username: '{username}' - access granted (tier: {tier}, max fans: {max_fans}, trial_used: {trial_used})")
            return {
                'success': True,
                'message': 'Active subscription',
                'subscription_info': {
                    'tier': tier,
                    'max_fans': max_fans,
                    'status': status,
                    'days_remaining': days_remaining,
                    'subscription_end': subscription_end,
                    'trial_used': trial_used,
                    'is_trial': is_trial
                }
            }
            
        except Exception as e:
            print(f"[ERROR] Exception while checking subscription for '{username}': {e}")
            import traceback
            print(f"[ERROR] Traceback: {traceback.format_exc()}")
            return {'success': False, 'message': f'Error checking subscription: {str(e)}'}
    
    def activate_free_trial(self, username):
        """Activate 1-day free trial for a username"""
        try:
            if not self.supabase:
                print("[ERROR] Supabase not initialized")
                return {'success': False, 'message': 'Supabase not initialized'}
            
            if not username or len(username.strip()) == 0:
                print("[ERROR] Invalid username provided")
                return {'success': False, 'message': 'Invalid username'}
            
            username = username.strip().lower()
            print(f"[TRIAL] Checking trial eligibility for: '{username}'")
            
            # Check if user already exists and has used trial
            response = self.supabase.table('subscriptions').select('*').eq('username', username).execute()
            
            if response.data:
                subscription_data = response.data[0]
                trial_used = subscription_data.get('trial_used', False)
                
                if trial_used:
                    print(f"[TRIAL] Trial already used for username: '{username}'")
                    return {'success': False, 'message': 'Free trial already used'}
                
                # Check if they have an active subscription
                status = subscription_data.get('status', 'inactive')
                if status == 'active':
                    print(f"[TRIAL] User already has active subscription: '{username}'")
                    return {'success': False, 'message': 'User already has active subscription'}
            
            # Calculate trial end date (1 day from now)
            trial_end = datetime.now() + timedelta(days=1)
            trial_end_str = trial_end.isoformat()
            
            # Create or update subscription with trial
            trial_data = {
                'username': username,
                'status': 'active',
                'tier': 'basic',  # Give them basic tier for trial (25 fans)
                'subscription_end': trial_end_str,
                'trial_used': True,
                'is_trial': True,
                'subscription_start': datetime.now().isoformat(),
                'payment_reference': f'TRIAL_{username}'
            }
            
            # Upsert the trial data
            self.supabase.table('subscriptions').upsert(trial_data).execute()
            
            print(f"[TRIAL] Free trial activated for username: '{username}' until {trial_end_str}")
            return {
                'success': True,
                'message': f'Free trial activated! You now have basic access (25 fans) until {trial_end_str}',
                'trial_end': trial_end_str,
                'tier': 'basic'
            }
            
        except Exception as e:
            print(f"[ERROR] Failed to activate trial for '{username}': {e}")
            import traceback
            print(f"[ERROR] Traceback: {traceback.format_exc()}")
            return {'success': False, 'message': f'Error activating trial: {str(e)}'}
    
    def activate_subscription(self, username, payment_reference=None, tier='basic'):
        """Activate subscription for username"""
        try:
            if not self.supabase:
                print("[ERROR] Supabase not initialized")
                return False
            
            if not username or len(username.strip()) == 0:
                print("[ERROR] Invalid username provided")
                return False
            
            username = username.strip().lower()  # Normalize username
            
            # Calculate subscription dates
            start_date = datetime.now()
            end_date = start_date + timedelta(days=30)  # 30 days subscription
            
            # Get current pricing
            pricing = self.get_current_pricing()
            monthly_price = pricing['monthly_price']
            currency = pricing['currency']
            
            # Prepare subscription data
            subscription_data = {
                'username': username,
                'status': 'active',
                'subscription_start': start_date.isoformat(),
                'subscription_end': end_date.isoformat(),
                'last_payment': start_date.isoformat(),
                'price': monthly_price,
                'currency': currency,
                'payment_reference': payment_reference or f"USERNAME_{username}",
                'tier': tier,
                'trial_used': False,
                'is_trial': False
            }
            
            # Upsert to Supabase
            self.supabase.table('subscriptions').upsert(subscription_data).execute()
            
            print(f"[SUCCESS] Subscription activated for username: {username} with tier: {tier}")
            print(f"[INFO] Subscription valid until: {end_date.strftime('%Y-%m-%d')}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Error activating subscription for {username}: {e}")
            return False
    
    def get_current_pricing(self):
        """Get current pricing from Supabase"""
        try:
            if not self.supabase:
                return {
                    'monthly_price': 19.99,
                    'currency': 'EUR',
                    'source': 'fallback'
                }
            
            # Get pricing from Supabase
            response = self.supabase.table('config').select('data').eq('id', 'pricing').execute()
            
            if response.data:
                pricing_data = response.data[0]['data']
                return {
                    'monthly_price': float(pricing_data.get('monthly_price', 19.99)),
                    'currency': pricing_data.get('currency', 'EUR'),
                    'source': 'supabase_remote'
                }
            else:
                return {
                    'monthly_price': 19.99,
                    'currency': 'EUR',
                    'source': 'fallback'
                }
                
        except Exception as e:
            print(f"[ERROR] Error getting pricing from Supabase: {e}")
            return {
                'monthly_price': 19.99,
                'currency': 'EUR',
                'source': 'fallback_error'
            }

    def get_payment_details(self):
        """Get current payment details from Supabase"""
        try:
            if not self.supabase:
                return {
                    'iban': 'CONTACT_DEVELOPER',
                    'bic': 'CONTACT_DEV',
                    'beneficiary': 'Contact Developer',
                    'source': 'fallback'
                }
            
            # Get payment details from Supabase
            response = self.supabase.table('config').select('data').eq('id', 'payment_details').execute()
            
            if response.data:
                payment_data = response.data[0]['data']
                return {
                    'iban': payment_data.get('iban', 'CONTACT_DEVELOPER'),
                    'bic': payment_data.get('bic', 'CONTACT_DEV'),
                    'beneficiary': payment_data.get('beneficiary', 'Contact Developer'),
                    'source': 'supabase_remote'
                }
            else:
                return {
                    'iban': 'CONTACT_DEVELOPER',
                    'bic': 'CONTACT_DEV',
                    'beneficiary': 'Contact Developer',
                    'source': 'fallback'
                }
                
        except Exception as e:
            print(f"[ERROR] Error getting payment details from Supabase: {e}")
            return {
                'iban': 'CONTACT_DEVELOPER',
                'bic': 'CONTACT_DEV',
                'beneficiary': 'Contact Developer',
                'source': 'fallback_error'
            }
    
    def _update_subscription_status(self, username, status):
        """Internal method to update subscription status"""
        try:
            if not self.supabase:
                return False
            
            username = username.strip().lower()
            
            self.supabase.table('subscriptions').update({
                'status': status,
                'updated_at': datetime.now().isoformat()
            }).eq('username', username).execute()
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Error updating status for {username}: {e}")
            return False
    
    def verify_admin_credentials(self, admin_key):
        """Verify admin access credentials against Supabase"""
        try:
            if not self.supabase:
                print("[ERROR] Supabase not initialized for admin verification")
                return {'success': False, 'message': 'Supabase not initialized'}
            
            # Get admin configuration from Supabase
            response = self.supabase.table('admin').select('*').eq('id', 'auth').execute()
            
            if not response.data:
                print("[ERROR] Admin authentication document not found")
                return {'success': False, 'message': 'Admin authentication not configured'}
            
            admin_data = response.data[0]
            stored_key = admin_data.get('admin_key')
            
            if not stored_key:
                print("[ERROR] Admin key not found in Supabase")
                return {'success': False, 'message': 'Admin key not configured'}
            
            if admin_key != stored_key:
                print("[WARNING] Invalid admin key attempted")
                return {'success': False, 'message': 'Invalid admin credentials'}
            
            print("[INFO] Admin authentication successful")
            return {'success': True, 'message': 'Admin authenticated successfully'}
            
        except Exception as e:
            print(f"[ERROR] Admin authentication failed: {e}")
            return {'success': False, 'message': 'Authentication error'}
    
    def create_admin_auth(self, admin_key):
        """Create or update admin authentication in Supabase"""
        try:
            if not self.supabase:
                print("[ERROR] Supabase not initialized")
                return {'success': False, 'message': 'Supabase not initialized'}
            
            # Store admin key in Supabase
            admin_data = {
                'id': 'auth',
                'admin_key': admin_key,
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            self.supabase.table('admin').upsert(admin_data).execute()
            
            print("[INFO] Admin authentication configured successfully")
            return {'success': True, 'message': 'Admin authentication configured'}
            
        except Exception as e:
            print(f"[ERROR] Failed to create admin auth: {e}")
            return {'success': False, 'message': 'Failed to configure admin authentication'}
    
    def get_discord_webhook(self):
        """Get Discord webhook URL from Supabase"""
        try:
            if not self.supabase:
                return None
            
            response = self.supabase.table('config').select('*').eq('id', 'discord_webhook').execute()
            
            if response.data:
                # Check if the data is already the webhook URL or if it's in a data field
                record = response.data[0]
                if isinstance(record, dict):
                    # If record has a 'data' field, extract the webhook from there
                    if 'data' in record and isinstance(record['data'], dict):
                        return record['data'].get('webhook_url')
                    # If record directly has webhook_url, return it
                    elif 'webhook_url' in record:
                        return record['webhook_url']
                    # If record is the webhook data itself
                    else:
                        return record.get('webhook_url')
                else:
                    # Handle case where record might be a string or other type
                    print(f"[WARNING] Unexpected data format for Discord webhook: {type(record)}")
                    return None
            
            return None
            
        except Exception as e:
            print(f"[ERROR] Error getting Discord webhook: {e}")
            return None
    
    def get_payment_proof_webhook(self):
        """Get payment proof webhook URL from Supabase"""
        try:
            if not self.supabase:
                return None
            
            response = self.supabase.table('config').select('*').eq('id', 'payment_proof_webhook').execute()
            
            if response.data:
                # Check if the data is already the webhook URL or if it's in a data field
                record = response.data[0]
                if isinstance(record, dict):
                    # If record has a 'data' field, extract the webhook from there
                    if 'data' in record and isinstance(record['data'], dict):
                        return record['data'].get('webhook_url')
                    # If record directly has webhook_url, return it
                    elif 'webhook_url' in record:
                        return record['webhook_url']
                    # If record is the webhook data itself
                    else:
                        return record.get('webhook_url')
                else:
                    # Handle case where record might be a string or other type
                    print(f"[WARNING] Unexpected data format for payment proof webhook: {type(record)}")
                    return None
            
            return None
            
        except Exception as e:
            print(f"[ERROR] Error getting payment proof webhook: {e}")
            return None
    
    def update_discord_webhook(self, webhook_url):
        """Update Discord webhook URL in Supabase"""
        try:
            if not self.supabase:
                print("[ERROR] Supabase not initialized")
                return False
                
            # Prepare webhook data with the same structure as other config items
            webhook_data = {
                'id': 'discord_webhook',
                'data': {
                    'webhook_url': webhook_url,
                    'updated_at': datetime.now().isoformat()
                }
            }
            
            # Update webhook in Supabase config table
            self.supabase.table('config').upsert(webhook_data).execute()
            
            print(f"[INFO] Discord webhook updated successfully")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to update Discord webhook: {e}")
            return False
    
    def update_payment_proof_webhook(self, webhook_url):
        """Update payment proof webhook URL in Supabase"""
        try:
            if not self.supabase:
                print("[ERROR] Supabase not initialized")
                return False
                
            # Prepare webhook data with the same structure as other config items
            webhook_data = {
                'id': 'payment_proof_webhook',
                'data': {
                    'webhook_url': webhook_url,
                    'updated_at': datetime.now().isoformat()
                }
            }
            
            # Update webhook in Supabase config table
            self.supabase.table('config').upsert(webhook_data).execute()
            
            print(f"[INFO] Payment proof webhook updated successfully")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to update payment proof webhook: {e}")
            return False
    
    def list_all_subscriptions(self):
        """List all subscriptions from Supabase"""
        try:
            if not self.supabase:
                print("[ERROR] Supabase not initialized")
                return []
            
            response = self.supabase.table('subscriptions').select('*').execute()
            return response.data or []
            
        except Exception as e:
            print(f"[ERROR] Error listing subscriptions: {e}")
            return []
    
    def get_all_users(self):
        """Get all users from Supabase"""
        try:
            if not self.supabase:
                print("[ERROR] Supabase not initialized")
                return []
            
            print("[DEBUG] LicenseManager.get_all_users() - querying users table")
            # Always use the basic query that works
            response = self.supabase.table('users').select('username, created_at').execute()
            print(f"[DEBUG] LicenseManager.get_all_users() - response: {response}")
            return response.data or []
            
        except Exception as e:
            print(f"[ERROR] Error getting users: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def update_pricing(self, price, currency='EUR'):
        """Update pricing configuration in Supabase"""
        try:
            if not self.supabase:
                print("[ERROR] Supabase not initialized")
                return False
                
            # Prepare pricing data
            pricing_data = {
                'id': 'pricing',
                'data': {
                    'monthly_price': float(price),
                    'currency': currency,
                    'updated_at': datetime.now().isoformat()
                }
            }
            
            # Update pricing in Supabase config table
            self.supabase.table('config').upsert(pricing_data).execute()
            
            print(f"[INFO] Pricing updated successfully: {price} {currency}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to update pricing: {e}")
            return False
            
    def update_payment_details(self, iban, bic, beneficiary):
        """Update payment details configuration in Supabase"""
        try:
            if not self.supabase:
                print("[ERROR] Supabase not initialized")
                return False
                
            # Prepare payment details data
            payment_data = {
                'id': 'payment_details',
                'data': {
                    'iban': iban,
                    'bic': bic,
                    'beneficiary': beneficiary,
                    'updated_at': datetime.now().isoformat()
                }
            }
            
            # Update payment details in Supabase config table
            self.supabase.table('config').upsert(payment_data).execute()
            
            print("[INFO] Payment details updated successfully")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to update payment details: {e}")
            return False
            
    def delete_subscription(self, username):
        """Delete subscription for a specific username from Supabase"""
        try:
            if not self.supabase:
                print("[ERROR] Supabase not initialized")
                return False
                
            if not username or len(username.strip()) == 0:
                print("[ERROR] Invalid username provided")
                return False
                
            username = username.strip().lower()
            
            # Delete subscription from Supabase
            response = self.supabase.table('subscriptions').delete().eq('username', username).execute()
            
            # Check if any rows were deleted
            deleted_count = len(response.data) if response.data else 0
            print(f"[INFO] Deleted {deleted_count} subscription(s) for username: {username}")
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to delete subscription for {username}: {e}")
            return False
    
    def delete_user(self, username):
        """Delete user account from Supabase"""
        try:
            if not self.supabase:
                print("[ERROR] Supabase not initialized")
                return False
                
            if not username or len(username.strip()) == 0:
                print("[ERROR] Invalid username provided")
                return False
                
            username = username.strip()
            
            # Delete user from Supabase
            response = self.supabase.table('users').delete().eq('username', username).execute()
            
            # Check if any rows were deleted
            deleted_count = len(response.data) if response.data else 0
            print(f"[INFO] Deleted {deleted_count} user(s) for username: {username}")
            
            return deleted_count > 0
            
        except Exception as e:
            print(f"[ERROR] Failed to delete user {username}: {e}")
            return False
    
    @property
    def db(self):
        """Provide db property for compatibility with admin routes"""
        return self.supabase

# Test function
def test_supabase_connection():
    """Test Supabase connection"""
    try:
        lm = LicenseManager()
        
        if lm.supabase:
            print("✅ Supabase connection successful")
            
            # Test pricing
            pricing = lm.get_current_pricing()
            print(f"✅ Pricing test: {pricing}")
            
            # Test payment details  
            payment = lm.get_payment_details()
            print(f"✅ Payment details test: {payment}")
            
            return True
        else:
            print("❌ Supabase connection failed")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    test_supabase_connection()