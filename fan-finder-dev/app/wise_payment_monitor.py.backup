#!/usr/bin/env python3
"""
Wise Payment Monitor for Fan Finder
Monitors Wise account for incoming payments and automatically activates subscriptions
"""

import os
import sys
import time
import json
import requests
import schedule
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from secure_config import get_wise_api_key, get_wise_bank_details
from firebase_admin import firestore
import logging
from backend.license_manager import LicenseManager

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WisePaymentMonitor:
    def __init__(self):
        self.api_key = get_wise_api_key()
        self.base_url = "https://api.wise.com"
        self.sandbox_url = "https://api.sandbox.transferwise.tech"  # For testing
        
        # Use sandbox for now, production when bank details are available
        self.current_url = self.sandbox_url
        
        self.profile_id = None
        self.account_balances = {}
        self.last_check_time = datetime.now() - timedelta(hours=1)
        
        # Initialize Firebase for subscription management
        self._init_firebase()
        
        # Initialize LicenseManager to handle subscription activation
        self.license_manager = LicenseManager()
        
    def _init_firebase(self):
        """Initialize Firebase connection"""
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
            
            if not firebase_admin._apps:
                # Firebase should already be initialized by the main app
                pass
            
            self.db = firestore.client()
            logger.info("Firebase initialized for payment monitoring")
            
        except Exception as e:
            logger.error(f"Firebase initialization failed: {e}")
            self.db = None
    
    def get_profile(self) -> Optional[int]:
        """Get user profile ID"""
        if not self.api_key:
            logger.error("Wise API key not found")
            return None
            
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(f"{self.current_url}/v1/profiles", headers=headers)
            
            if response.status_code == 200:
                profiles = response.json()
                if profiles:
                    self.profile_id = profiles[0]['id']
                    logger.info(f"Profile ID obtained: {self.profile_id}")
                    return self.profile_id
            else:
                logger.error(f"Failed to get profile: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"Error getting profile: {e}")
            
        return None
    
    def get_account_balances(self) -> Dict:
        """Get account balances"""
        if not self.profile_id:
            if not self.get_profile():
                return {}
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(
                f"{self.current_url}/v4/profiles/{self.profile_id}/balances",
                headers=headers
            )
            
            if response.status_code == 200:
                balances = response.json()
                balance_dict = {}
                
                for balance in balances:
                    currency = balance['currency']
                    balance_dict[currency] = {
                        'id': balance['id'],
                        'amount': balance['amount']['value'],
                        'currency': currency
                    }
                
                self.account_balances = balance_dict
                logger.info(f"Account balances retrieved: {list(balance_dict.keys())}")
                return balance_dict
            else:
                logger.error(f"Failed to get balances: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"Error getting balances: {e}")
            
        return {}
    
    def get_balance_transactions(self, balance_id: int, since: datetime) -> List[Dict]:
        """Get transactions for a specific balance since a given time"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # Convert datetime to ISO format
            since_str = since.strftime('%Y-%m-%dT%H:%M:%SZ')
            
            response = requests.get(
                f"{self.current_url}/v1/profiles/{self.profile_id}/balance-statements/{balance_id}",
                headers=headers,
                params={
                    'intervalStart': since_str,
                    'intervalEnd': datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('transactions', [])
            else:
                logger.warning(f"Failed to get transactions: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error getting transactions: {e}")
            
        return []
    
    def process_incoming_payment(self, transaction: Dict) -> bool:
        """Process an incoming payment transaction"""
        try:
            # Extract payment details
            amount = transaction.get('amount', {}).get('value', 0)
            currency = transaction.get('amount', {}).get('currency', '')
            reference = transaction.get('details', {}).get('description', '')
            transaction_id = transaction.get('referenceNumber', '')
            
            logger.info(f"Processing payment: {currency} {amount}, ref: {reference}")
            
            # Check if this is a Fan Finder subscription payment
            if self.is_fanfinder_payment(reference, amount, currency):
                username = self.extract_username_from_reference(reference)
                if username:
                    success = self.activate_subscription(username, amount, currency, transaction_id)
                    if success:
                        logger.info(f"✅ Subscription activated for user: {username}")
                        self.send_activation_notification(username)
                        return True
                    else:
                        logger.error(f"❌ Failed to activate subscription for user: {username}")
            else:
                logger.info("Payment not identified as Fan Finder subscription")
                
        except Exception as e:
            logger.error(f"Error processing payment: {e}")
            
        return False
    
    def is_fanfinder_payment(self, reference: str, amount: float, currency: str) -> bool:
        """Check if payment matches Fan Finder subscription criteria"""
        # Check reference format (FF-, fanfinder, etc.)
        reference_lower = reference.lower()
        valid_references = ['ff-', 'fanfinder', 'fan finder', 'fan-finder']
        
        has_valid_reference = any(ref in reference_lower for ref in valid_references)
        
        # Check amount (get current pricing from Firebase)
        valid_amount = self.is_valid_subscription_amount(amount, currency)
        
        return has_valid_reference and valid_amount
    
    def is_valid_subscription_amount(self, amount: float, currency: str) -> bool:
        """Check if amount matches subscription pricing"""
        try:
            # Get current pricing from Firebase
            if self.db:
                doc_ref = self.db.collection('config').document('pricing')
                doc = doc_ref.get()
                
                if doc.exists:
                    pricing = doc.to_dict()
                    expected_amount = float(pricing.get('monthly_price', 20))
                    expected_currency = pricing.get('currency', 'EUR')
                    
                    # Allow for small variations in amount (fees, etc.)
                    amount_diff = abs(amount - expected_amount)
                    currency_match = currency.upper() == expected_currency.upper()
                    
                    return currency_match and amount_diff <= 2.0  # Allow 2 EUR difference
            
            # Fallback pricing
            return currency.upper() == 'EUR' and 18.0 <= amount <= 25.0
            
        except Exception as e:
            logger.error(f"Error checking subscription amount: {e}")
            return False
    
    def extract_username_from_reference(self, reference: str) -> Optional[str]:
        """Extract username from payment reference"""
        try:
            reference = reference.strip()
            
            # Try different reference formats:
            # FF-username-timestamp-uniqueid
            # fanfinder-username
            # username (if other validation passed)
            
            if reference.startswith('FF-'):
                parts = reference.split('-')
                if len(parts) >= 2:
                    return parts[1]
            
            if 'fanfinder' in reference.lower():
                # Try to extract username after fanfinder
                ref_lower = reference.lower()
                if '-' in ref_lower:
                    parts = reference.split('-')
                    for i, part in enumerate(parts):
                        if 'fanfinder' in part.lower() and i + 1 < len(parts):
                            return parts[i + 1]
            
            # If no clear pattern, try to find email-like patterns
            if '@' in reference:
                return reference.split('@')[0]
            
            # Last resort - use the whole reference as username
            return reference[:50]  # Limit length
            
        except Exception as e:
            logger.error(f"Error extracting username: {e}")
            return None
    
    def activate_subscription(self, username: str, amount: float, currency: str, transaction_id: str) -> bool:
        """Activate subscription for user"""
        try:
            # Determine the subscription tier based on the payment amount
            tier = self._determine_tier_from_amount(amount)
            
            # Use LicenseManager to activate the subscription in Supabase
            success = self.license_manager.activate_subscription(
                username, 
                payment_reference=transaction_id, 
                tier=tier
            )
            
            if success:
                logger.info(f"Subscription activated: {username} with tier {tier} for amount {amount} {currency}")
                return True
            else:
                logger.error(f"Failed to activate subscription in Supabase for {username}")
                return False
            
        except Exception as e:
            logger.error(f"Error activating subscription: {e}")
            return False
    
    def _determine_tier_from_amount(self, amount: float) -> str:
        """Determine subscription tier based on payment amount"""
        try:
            # Get current pricing configuration to determine thresholds
            pricing = self.license_manager.get_current_pricing()
            monthly_price = pricing['monthly_price']
            
            # Determine tier based on multiples of monthly price
            # Basic: 1x monthly price
            # Pro: ~6x monthly price 
            # Premium: ~12x monthly price (for yearly plan, unlimited access)
            basic_threshold = monthly_price * 1.5  # Allow some variation for fees
            pro_threshold = monthly_price * 5    # 6 months with possible discount
            premium_threshold = monthly_price * 10  # 12 months with possible discount
            
            if amount >= premium_threshold:
                return 'premium'
            elif amount >= pro_threshold:
                return 'pro'
            else:
                return 'basic'
                
        except Exception as e:
            logger.error(f"Error determining tier from amount {amount}: {e}")
            # Default to basic if there's an error
            return 'basic'
    
    def send_activation_notification(self, username: str):
        """Send notification about subscription activation"""
        try:
            # This would integrate with your existing notification system
            # For now, just log it
            logger.info(f"🎉 NOTIFICATION: Subscription activated for {username}")
            
            # TODO: Add email notification
            # TODO: Add Discord webhook notification
            # TODO: Add in-app notification
            
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
    
    def monitor_payments(self):
        """Main monitoring function - checks for new payments"""
        try:
            logger.info("🔍 Checking for new payments...")
            
            # Get current balances
            balances = self.get_account_balances()
            
            if not balances:
                logger.warning("No balances found - API might be in sandbox mode")
                return
            
            # Check transactions for each currency
            for currency, balance_info in balances.items():
                balance_id = balance_info['id']
                transactions = self.get_balance_transactions(balance_id, self.last_check_time)
                
                logger.info(f"Found {len(transactions)} transactions in {currency} since last check")
                
                for transaction in transactions:
                    # Only process incoming credits
                    if transaction.get('type') == 'CREDIT':
                        self.process_incoming_payment(transaction)
            
            # Update last check time
            self.last_check_time = datetime.now()
            logger.info("✅ Payment monitoring cycle completed")
            
        except Exception as e:
            logger.error(f"Error in payment monitoring: {e}")
    
    def start_monitoring(self, interval_minutes: int = 5):
        """Start continuous payment monitoring"""
        logger.info(f"🚀 Starting Wise payment monitoring (every {interval_minutes} minutes)")
        
        # Schedule monitoring
        schedule.every(interval_minutes).minutes.do(self.monitor_payments)
        
        # Run initial check
        self.monitor_payments()
        
        # Keep running
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute for scheduled tasks

def main():
    """Main function to start payment monitoring"""
    print("🏦 Wise Payment Monitor for Fan Finder")
    print("=" * 50)
    
    monitor = WisePaymentMonitor()
    
    if not monitor.api_key:
        print("❌ ERROR: Wise API key not found!")
        print("Please run 'python store_wise_api_key.py' first")
        return
    
    print("✅ Wise API key loaded securely from Firebase")
    print("🔍 Starting payment monitoring...")
    print("💡 This will run continuously and check for payments every 5 minutes")
    print("🛑 Press Ctrl+C to stop")
    print()
    
    try:
        monitor.start_monitoring(interval_minutes=5)
    except KeyboardInterrupt:
        print("\n🛑 Payment monitoring stopped by user")
    except Exception as e:
        print(f"\n❌ Payment monitoring failed: {e}")

if __name__ == "__main__":
    main()