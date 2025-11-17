#!/usr/bin/env python3
"""
Security middleware for Fan Finder Application
Provides additional security layers to prevent unauthorized access
"""

import os
import hashlib
import time
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, g
import sqlite3
import json

class SecurityManager:
    """Additional security layer for the application"""
    
    def __init__(self):
        self.security_db_path = 'security.db'
        self.init_security_db()
        
    def init_security_db(self):
        """Initialize local security database"""
        try:
            with sqlite3.connect(self.security_db_path) as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS access_attempts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ip_address TEXT,
                        user_agent TEXT,
                        endpoint TEXT,
                        timestamp DATETIME,
                        success BOOLEAN,
                        fingerprint TEXT
                    )
                ''')
                
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS app_instances (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        machine_fingerprint TEXT UNIQUE,
                        first_seen DATETIME,
                        last_seen DATETIME,
                        access_count INTEGER DEFAULT 1,
                        is_authorized BOOLEAN DEFAULT TRUE
                    )
                ''')
                conn.commit()
        except Exception as e:
            print(f"[SECURITY] Warning: Could not initialize security database: {e}")
    
    def get_machine_fingerprint(self):
        """Generate unique machine fingerprint"""
        try:
            # Combine multiple system identifiers
            import platform
            import getpass
            
            # Get system information
            machine_id = platform.machine()
            system = platform.system()
            node = platform.node()
            processor = platform.processor()
            username = getpass.getuser()
            
            # Combine all identifiers
            fingerprint_data = f"{machine_id}-{system}-{node}-{processor}-{username}"
            
            # Hash the combined data
            return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:32]
        except Exception as e:
            print(f"[SECURITY] Warning: Could not generate machine fingerprint: {e}")
            return "unknown"
    
    def log_access_attempt(self, ip_address, user_agent, endpoint, success=True):
        """Log access attempt with machine fingerprint"""
        try:
            fingerprint = self.get_machine_fingerprint()
            
            with sqlite3.connect(self.security_db_path) as conn:
                conn.execute('''
                    INSERT INTO access_attempts 
                    (ip_address, user_agent, endpoint, timestamp, success, fingerprint)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (ip_address, user_agent, endpoint, datetime.now(), success, fingerprint))
                
                # Update or create app instance record
                conn.execute('''
                    INSERT OR REPLACE INTO app_instances 
                    (machine_fingerprint, first_seen, last_seen, access_count)
                    VALUES (?, 
                            COALESCE((SELECT first_seen FROM app_instances WHERE machine_fingerprint = ?), ?),
                            ?,
                            COALESCE((SELECT access_count FROM app_instances WHERE machine_fingerprint = ?), 0) + 1)
                ''', (fingerprint, fingerprint, datetime.now(), datetime.now(), fingerprint))
                
                conn.commit()
        except Exception as e:
            print(f"[SECURITY] Warning: Could not log access attempt: {e}")
    
    def check_rate_limit(self, ip_address, max_requests=100, time_window_minutes=60):
        """Check if IP address is within rate limits"""
        try:
            cutoff_time = datetime.now() - timedelta(minutes=time_window_minutes)
            
            with sqlite3.connect(self.security_db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM access_attempts 
                    WHERE ip_address = ? AND timestamp > ?
                ''', (ip_address, cutoff_time))
                
                request_count = cursor.fetchone()[0]
                return request_count < max_requests
        except Exception as e:
            print(f"[SECURITY] Warning: Could not check rate limit: {e}")
            return True  # Allow access if we can't check
    
    def is_suspicious_request(self, request):
        """Check if request appears suspicious"""
        suspicious_patterns = [
            # Common attack patterns
            'union select', 'drop table', 'insert into', 'delete from',
            '../', '<script>', 'javascript:', 'vbscript:',
            'cmd.exe', '/bin/bash', 'powershell',
            # API abuse patterns
            'bot', 'crawler', 'scraper', 'spider'
        ]
        
        # Check user agent
        user_agent = request.headers.get('User-Agent', '').lower()
        
        # Check if it's a legitimate browser or our app
        legitimate_patterns = ['chrome', 'firefox', 'safari', 'edge', 'python-requests']
        is_legitimate = any(pattern in user_agent for pattern in legitimate_patterns)
        
        if not is_legitimate:
            return True
        
        # Check for suspicious patterns in various request parts
        check_strings = [
            request.path.lower(),
            str(request.args).lower(),
            user_agent
        ]
        
        for check_str in check_strings:
            if any(pattern in check_str for pattern in suspicious_patterns):
                return True
        
        return False
    
    def security_check_required(self, f):
        """Decorator to add security checks to endpoints"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get client information
            ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', 'unknown'))
            user_agent = request.headers.get('User-Agent', 'unknown')
            endpoint = request.endpoint or request.path
            
            # Check rate limits
            if not self.check_rate_limit(ip_address):
                self.log_access_attempt(ip_address, user_agent, endpoint, success=False)
                return jsonify({'error': 'Rate limit exceeded. Please try again later.'}), 429
            
            # Check for suspicious requests
            if self.is_suspicious_request(request):
                self.log_access_attempt(ip_address, user_agent, endpoint, success=False)
                return jsonify({'error': 'Request blocked for security reasons.'}), 403
            
            # Log successful access
            self.log_access_attempt(ip_address, user_agent, endpoint, success=True)
            
            # Store security context for use in the endpoint
            g.security_context = {
                'machine_fingerprint': self.get_machine_fingerprint(),
                'ip_address': ip_address,
                'user_agent': user_agent
            }
            
            return f(*args, **kwargs)
        return decorated_function
    
    def validate_local_access(self):
        """Verify this is a legitimate local installation"""
        try:
            # Check if this appears to be a local installation
            fingerprint = self.get_machine_fingerprint()
            
            with sqlite3.connect(self.security_db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT is_authorized, access_count FROM app_instances 
                    WHERE machine_fingerprint = ?
                ''', (fingerprint,))
                
                result = cursor.fetchone()
                
                if result is None:
                    # New installation, automatically authorize
                    return True
                
                is_authorized, access_count = result
                
                # Check for suspicious usage patterns
                if access_count > 10000:  # Unusually high usage
                    print(f"[SECURITY] Warning: High usage count detected: {access_count}")
                
                return is_authorized
        except Exception as e:
            print(f"[SECURITY] Warning: Could not validate local access: {e}")
            return True  # Allow access if we can't validate
    
    def get_security_stats(self):
        """Get security statistics (for admin purposes)"""
        try:
            with sqlite3.connect(self.security_db_path) as conn:
                cursor = conn.cursor()
                
                # Get total access attempts
                cursor.execute('SELECT COUNT(*) FROM access_attempts')
                total_attempts = cursor.fetchone()[0]
                
                # Get failed attempts in last 24 hours
                yesterday = datetime.now() - timedelta(hours=24)
                cursor.execute('SELECT COUNT(*) FROM access_attempts WHERE success = 0 AND timestamp > ?', (yesterday,))
                failed_attempts = cursor.fetchone()[0]
                
                # Get unique IPs in last 24 hours
                cursor.execute('SELECT COUNT(DISTINCT ip_address) FROM access_attempts WHERE timestamp > ?', (yesterday,))
                unique_ips = cursor.fetchone()[0]
                
                return {
                    'total_attempts': total_attempts,
                    'failed_attempts_24h': failed_attempts,
                    'unique_ips_24h': unique_ips,
                    'machine_fingerprint': self.get_machine_fingerprint()
                }
        except Exception as e:
            print(f"[SECURITY] Warning: Could not get security stats: {e}")
            return {}

# Global security manager instance
security_manager = SecurityManager()