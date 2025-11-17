#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# app.py - Main Flask server for Fan Finder Application

import sys
import os
# Force UTF-8 encoding on Windows
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

import psutil
import subprocess
import threading
import time
import json
import atexit
import signal
import requests
import logging
import secrets
import hashlib
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask

# Suppress Flask development server warning
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# Test imports first
try:
    from flask import Flask, request, jsonify, send_from_directory
    from flask_socketio import SocketIO, emit, join_room
    from flask_cors import CORS
    from dotenv import load_dotenv
    from license_manager import LicenseManager
    from security_middleware import security_manager
except Exception as e:
    print("❌ Import error - missing required packages")
    print("Please run the startup script to install dependencies")
    sys.exit(1)

# Load environment variables
load_dotenv()
print("[STARTING] Fan Finder Web Server...")

# Discord webhook will be loaded dynamically from Firebase

def get_discord_webhook():
    """Get current Discord webhook URL from Firebase"""
    try:
        lm = get_license_manager()
        webhook_data = lm.get_discord_webhook()
        # Handle case where webhook_data might be a string, dict, or None
        if isinstance(webhook_data, str):
            return webhook_data
        elif isinstance(webhook_data, dict):
            return webhook_data.get('webhook_url', '')
        else:
            return ''
    except Exception as e:
        print(f"[ERROR] Failed to get Discord webhook: {e}")
        return os.getenv('DISCORD_WEBHOOK_URL', '')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-change-this')
socketio = SocketIO(app, 
    cors_allowed_origins="*",
    ping_timeout=60,
    ping_interval=25,
    logger=False,
    engineio_logger=False,
    async_mode='threading'
)
CORS(app)

# Test route to verify routes work
@app.route('/api/debug-test')
def debug_test():
    return {'success': True, 'message': 'Routes are working correctly'}

# Simple auth routes without security middleware
@app.route('/api/simple/signup', methods=['POST'])
def simple_signup():
    """Simple signup without security middleware"""
    try:
        data = request.get_json() or {}
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'success': False, 'message': 'Username and password required'})
        
        if auth_manager is None:
            return jsonify({'success': False, 'message': 'Authentication system not available'})
        
        result = auth_manager.create_user(username, password)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/simple/signin', methods=['POST'])
def simple_signin():
    """Simple signin without security middleware"""
    try:
        data = request.get_json() or {}
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'success': False, 'message': 'Username and password required'})
        
        if auth_manager is None:
            return jsonify({'success': False, 'message': 'Authentication system not available'})
        
        result = auth_manager.authenticate_user(username, password)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

print("[OK] Web server initialized")

# Global license manager will be initialized lazily
license_manager = None

def get_license_manager():
    """Get or create license manager instance"""
    global license_manager
    if license_manager is None:
        license_manager = LicenseManager()
    return license_manager

# VNC WebSocket Proxy for browser-based VNC
import socket
import select
import threading
import base64

# Store VNC connections per client
vnc_connections = {}

# Basic WebSocket connection handlers
@socketio.on('connect')
def handle_connect():
    print(f"[WEBSOCKET] Client connected: {request.sid}")
    emit('connection_confirmed', {
        'status': 'connected',
        'message': 'WebSocket connection established successfully',
        'client_id': request.sid
    })

@socketio.on('disconnect')
def handle_disconnect():
    print(f"[WEBSOCKET] Client disconnected: {request.sid}")

# VNC WebSocket handlers - moved to main level for proper registration
@socketio.on('vnc_connect')
def handle_vnc_connect(data=None):
    client_id = request.sid
    try:
        # Check if VNC server is available
        vnc_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        vnc_socket.settimeout(5)
        vnc_socket.connect(('127.0.0.1', 5900))
        
        # Store connection
        vnc_connections[client_id] = vnc_socket
        
        emit('vnc_status', {
            'status': 'connected', 
            'message': 'Connected to VNC server successfully'
        })
        
    except Exception as e:
        emit('vnc_status', {
            'status': 'error', 
            'message': f'Cannot connect to VNC server: {str(e)}'
        })

@socketio.on('vnc_test')
def handle_vnc_test():
    emit('vnc_test_response', {
        'message': 'VNC WebSocket test successful! Connection is working.'
    })

@socketio.on('vnc_disconnect')
def handle_vnc_disconnect():
    client_id = request.sid
    
    if client_id in vnc_connections:
        try:
            vnc_connections[client_id].close()
        except:
            pass
        del vnc_connections[client_id]
    
    emit('vnc_status', {
        'status': 'disconnected', 
        'message': 'Disconnected from VNC server'
    }) 
# Global variables to track running processes
running_process = None
current_script_type = None
connected_clients = set()
# Track multiple instances: {f'{script_type}-{instance_num}': process}
running_instances = {}

class ScriptRunner:
    """Handles running automation scripts with real-time output"""

    def __init__(self, script_type, settings, socket_id, instance_number=1):
        self.script_type = script_type
        self.settings = settings
        self.socket_id = socket_id
        self.instance_number = instance_number
        self.instance_key = f'{script_type}-{instance_number}'
        self.process = None
        # Create a consistent log prefix for this instance
        script_name = 'DISCOVERY' if script_type == 'discovery' else 'KEYWORD'
        self.log_prefix = f"[{script_name} INSTANCE {instance_number}]"
        
        
    def run(self):
        """Run the automation script"""
        global running_process, current_script_type, running_instances

        try:
            print(f"{self.log_prefix} [STARTING] {self.script_type.title()} script...")
            data = {"content": f"{self.script_type} script started...","username": "FanFindr"}
            webhook_url = get_discord_webhook()
            if webhook_url:
                try:
                    requests.post(webhook_url, json=data, timeout=5)
                except:
                    pass  # Don't break script startup for webhook failures
            # Get current working directory
            current_dir = os.getcwd()
            
            # Try multiple possible script paths
            script_name = 'discoverySearch.py' if self.script_type == 'discovery' else 'keywordSearch.py'
            
            possible_paths = [
                os.path.join('app', 'scripts', script_name),     # app/scripts/discoverySearch.py (from root)
                os.path.join('..', 'scripts', script_name),      # ../scripts/discoverySearch.py (from backend)
                os.path.join('scripts', script_name),            # scripts/discoverySearch.py (legacy)
                os.path.join('..', '..', 'scripts', script_name), # ../../scripts/discoverySearch.py (legacy)
                script_name  # Just the script name in current directory
            ]
            
            script_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    script_path = path
                    break
            
            if not script_path:
                error_msg = f"[ERROR] {script_name} not found in expected locations"
                print(error_msg)
                
                # Send detailed error to web interface
                with app.app_context():
                    socketio.emit('script_output', {
                        'script_type': self.script_type,
                        'output': f"[ERROR] {script_name} not found!",
                        'timestamp': datetime.now().strftime('%H:%M:%S')
                    })

                    # Emit script_stopped to reset UI button state
                    socketio.emit('script_stopped', {
                        'script_type': self.script_type,
                        'instance_number': self.instance_number,
                        'timestamp': datetime.now().isoformat()
                    })

                    socketio.emit('script_error', {
                        'script_type': self.script_type,
                        'instance_number': self.instance_number,
                        'error': f"Script {script_name} not found in any expected location",
                        'timestamp': datetime.now().isoformat()
                    }, room=self.socket_id)

                # Clear instance state
                if self.instance_key in running_instances:
                    del running_instances[self.instance_key]
                return
            
            # Build command arguments to run scripts directly
            # Use system Python to execute scripts so Chrome can appear on desktop
            python_exe = 'python3' if sys.platform != 'win32' else 'python'
            args = [python_exe, script_path]

            # Add model ID for credential fetching
            args.extend(['--model-id', self.settings['model_id']])
            args.extend(['--target-users', str(self.settings['target_users'])])

            # Add script-specific arguments
            if self.script_type == 'discovery':
                args.extend(['--posts-per-filter', str(self.settings.get('posts_per_filter', 100))])
            elif self.script_type == 'keyword':
                args.extend(['--posts-per-keyword', str(self.settings.get('posts_per_keyword', 50))])

            # Add browser settings (default to showing browser for better user experience)
            if self.settings.get('headless', False):
                args.append('--headless')

            args.append('--gui')  # Keep GUI flag for compatibility

            print(f"{self.log_prefix} [DEBUG] Full command: {args[0]} {args[1]} --model-id {self.settings['model_id']} {' '.join(args[3:])}")

            # Send initial messages to web interface
            with app.app_context():
                socketio.emit('script_output', {
                    'script_type': self.script_type,
                    'output': f"{self.log_prefix} 🚀 Starting {self.script_type} script...",
                    'timestamp': datetime.now().strftime('%H:%M:%S')
                }, room=self.socket_id)
            
            # Set environment variables for desktop Chrome
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            env['PYTHONUTF8'] = '1'
            env['PYTHONUNBUFFERED'] = '1'
            # Remove Docker-specific display - use system display for desktop Chrome
            
            # Start the process
            self.process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                env=env,
                bufsize=0,
                universal_newlines=True
            )
            
            # Track this instance's running process
            running_instances[self.instance_key] = self.process
            # Keep backward compatibility with old global variables
            running_process = self.process
            current_script_type = self.script_type
            
            print(f"{self.log_prefix} [STARTED] Process started (PID: {self.process.pid})")

            with app.app_context():
                socketio.emit('script_output', {
                    'script_type': self.script_type,
                    'output': f"{self.log_prefix} [OK] Process started (PID: {self.process.pid})",
                    'timestamp': datetime.now().strftime('%H:%M:%S')
                })

                # Note: script_started event is emitted by handle_start_script() with correct instance_number
                # Do NOT emit again here as it would cause duplicate events
            
            # Read output line by line with timeout
            collected_users = 0
            target_users = self.settings['target_users']
            line_count = 0
            no_output_count = 0

            while True:
                try:
                    line = self.process.stdout.readline()
                    
                    if not line:
                        if self.process.poll() is not None:
                            break
                        # ... existing no_output_count code ...
                        continue
                    
                    no_output_count = 0
                    clean_line = line.strip()
                    
                    if clean_line:
                        line_count += 1
                        
                        # Print important output to server console
                        if any(keyword in clean_line.lower() for keyword in ['error', 'failed', 'exception', 'warning', 'collected user', 'new user found', 'completed', 'finished']):
                            print(f"[{self.script_type.upper()}] {clean_line}")
                        
                        # *** CRITICAL: Use app context for socketio emission ***
                        with app.app_context():
                            socketio.emit('script_output', {
                                'script_type': self.script_type,
                                'output': clean_line,
                                'timestamp': datetime.now().strftime('%H:%M:%S')
                            })
                        
                        # Check for user collection progress
                        import re

                        # Check for user collection: either "Collected user:" or "New user found:"
                        progress_match = re.search(r'(?:collected user|new user found):\s*([^\s]+)\s*\((\d+)/(\d+)\s*-\s*([\d.]+)%\)', clean_line, re.IGNORECASE)

                        if progress_match:
                            try:
                                match = progress_match
                                username = match.group(1)
                                collected_users = int(match.group(2))
                                target_users = int(match.group(3))
                                progress = float(match.group(4))
                                
                                print(f"{self.log_prefix} [USER FOUND] {username} - Progress: {collected_users}/{target_users} ({progress}%)")
                                
                                # Use app context for emissions
                                with app.app_context():
                                    # Emit user collection event
                                    socketio.emit('user_collected', {
                                        'script_type': self.script_type,
                                        'instance_number': self.instance_number,
                                        'username': username,
                                        'timestamp': datetime.now().strftime('%H:%M:%S')
                                    })
                                    
                                    # Emit progress update
                                    socketio.emit('script_progress', {
                                        'script_type': self.script_type,
                                        'instance_number': self.instance_number,
                                        'collected_users': collected_users,
                                        'target_users': target_users,
                                        'progress': progress
                                    })
                                        
                            except Exception as e:
                                print(f"[DEBUG] Progress update error: {e}")
                
                except Exception as e:
                    print("[ERROR] Error reading output")
                    break
            
            # Wait for process to complete
            return_code = self.process.wait()

            # Clear instance state
            if self.instance_key in running_instances:
                del running_instances[self.instance_key]

            # Clear global state if no more instances running
            if not running_instances:
                running_process = None
                current_script_type = None
            
            status = '[COMPLETED]' if return_code == 0 else '[FAILED]'
            print(f"{self.log_prefix} {status} Script finished (exit code: {return_code})")

            # Send final messages
            if return_code == 0:
                final_message = f"{self.log_prefix} [OK] Script completed successfully! Collected {collected_users} users."
            else:
                final_message = f"{self.log_prefix} [ERROR] Script failed with return code {return_code}"
            
            # Broadcast to ALL connected clients
            with app.app_context():
                socketio.emit('script_output', {
                    'script_type': self.script_type,
                    'output': final_message,
                    'timestamp': datetime.now().strftime('%H:%M:%S')
                })

                # Emit script_stopped to notify frontend to update UI (instance finished or crashed)
                socketio.emit('script_stopped', {
                    'script_type': self.script_type,
                    'instance_number': self.instance_number,
                    'timestamp': datetime.now().isoformat()
                })

                # Emit completion to ALL clients
                socketio.emit('script_finished', {
                    'script_type': self.script_type,
                    'instance_number': self.instance_number,
                    'success': return_code == 0,
                    'return_code': return_code,
                    'collected_users': collected_users,
                    'timestamp': datetime.now().isoformat()
                })

                # Emit unblocked event for the other script type to ALL clients
                other_script_type = 'keyword' if self.script_type == 'discovery' else 'discovery'
                socketio.emit('script_unblocked', {
                    'script_type': other_script_type,
                    'timestamp': datetime.now().isoformat()
                })
            
        except Exception as e:
            error_msg = f"Script execution error: {str(e)}"
            print(f"{self.log_prefix} [ERROR] {error_msg}")

            # Clear instance state
            if self.instance_key in running_instances:
                del running_instances[self.instance_key]

            # Clear global state if no more instances running
            if not running_instances:
                running_process = None
                current_script_type = None
            
            # Broadcast error to ALL connected clients
            with app.app_context():
                socketio.emit('script_output', {
                    'script_type': self.script_type,
                    'output': f"[ERROR] EXCEPTION: {error_msg}",
                    'timestamp': datetime.now().strftime('%H:%M:%S')
                })

                # Emit script_stopped to reset UI button state
                socketio.emit('script_stopped', {
                    'script_type': self.script_type,
                    'instance_number': self.instance_number,
                    'timestamp': datetime.now().isoformat()
                })

                # Emit error to ALL clients
                socketio.emit('script_error', {
                    'script_type': self.script_type,
                    'instance_number': self.instance_number,
                    'error': error_msg,
                    'timestamp': datetime.now().isoformat()
                })
                
                # Emit unblocked event for the other script type to ALL clients
                other_script_type = 'keyword' if self.script_type == 'discovery' else 'discovery'
                socketio.emit('script_unblocked', {
                    'script_type': other_script_type,
                    'timestamp': datetime.now().isoformat()
                })

# API Routes
@app.route('/')
def index():
    """Serve the authentication page by default"""
    return send_from_directory('../frontend', 'auth.html')

@app.route('/api/test-post', methods=['POST'])
def test_post():
    """Test if POST works"""
    return jsonify({'success': True, 'message': 'POST works!'})

# Working login endpoint for the web app
@app.route('/api/user/login', methods=['POST'])
def working_user_login():
    """Working login endpoint for the web application"""
    try:
        # Get request data
        data = request.get_json() or {}
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'success': False, 'message': 'Username and password are required'})
        
        # Direct Supabase connection
        from license_manager import LicenseManager
        lm = LicenseManager()
        
        # Get user from database
        response = lm.supabase.table('users').select('*').eq('username', username).execute()
        
        if not response.data:
            return jsonify({'success': False, 'message': 'Invalid username or password'})
        
        user_data = response.data[0]
        stored_hash = user_data['password_hash']
        
        # Check password
        import hashlib
        provided_hash = hashlib.sha256(password.encode()).hexdigest()
        
        if stored_hash != provided_hash:
            return jsonify({'success': False, 'message': 'Invalid username or password'})
        
        # Generate auth token
        import secrets
        auth_token = secrets.token_urlsafe(64)
        
        # Success!
        return jsonify({
            'success': True,
            'token': auth_token,
            'user': {
                'username': username
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Login error: {str(e)}'})

# Authentication API endpoints - placed early to ensure registration
@app.route('/api/auth/signup', methods=['POST'])
def api_auth_signup():
    """Unified authentication endpoint - handles both signup and signin"""
    try:
        data = request.get_json() or {}
        username = data.get('username', '').strip()
        password = data.get('password', '')
        action = data.get('action', 'signup')
        
        # Debug output
        print(f"[UNIFIED] Action: {action}, Username: {username}")
        import sys
        sys.stdout.flush()
        
        if not username or not password:
            return jsonify({'success': False, 'message': 'Username and password are required'})
        
        if action == 'signin':
            # Handle signin
            from license_manager import LicenseManager
            lm = LicenseManager()

            response = lm.supabase.table('users').select('*').eq('username', username).execute()

            if not response.data:
                return jsonify({'success': False, 'message': 'Invalid username or password'})

            user_data = response.data[0]

            # CHECK IF USER IS APPROVED (THIS WAS MISSING!)
            is_approved = user_data.get('is_approved', False)  # Default to False - users must be approved
            if not is_approved:
                return jsonify({'success': False, 'message': 'Your account is pending approval. Please wait for admin approval.'})

            stored_hash = user_data['password_hash']

            # Check password
            import hashlib
            provided_hash = hashlib.sha256(password.encode()).hexdigest()

            if stored_hash != provided_hash:
                return jsonify({'success': False, 'message': 'Invalid username or password'})

            # Generate auth token
            import secrets
            auth_token = secrets.token_urlsafe(64)

            # Success!
            return jsonify({
                'success': True,
                'token': auth_token,
                'user': {
                    'username': username
                }
            })
        else:
            # Handle signup (original functionality)
            if len(username) < 3:
                return jsonify({'success': False, 'message': 'Username must be at least 3 characters long'})
            
            if len(password) < 6:
                return jsonify({'success': False, 'message': 'Password must be at least 6 characters long'})
            
            # Get global auth_manager for signup
            global auth_manager
            if not auth_manager:
                return jsonify({'success': False, 'message': 'Authentication system not available'})
            
            result = auth_manager.create_user(username, password)
            return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Authentication failed: {str(e)}'})

@app.route('/api/auth/signin', methods=['POST'])
def api_auth_signin():
    """User login API endpoint"""
    print("[AUTH] Signin API called")
    import sys
    sys.stdout.flush()
    try:
        data = request.get_json() or {}
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        print(f"[AUTH] Signin request - Username: {username}")
        sys.stdout.flush()
        
        if not username or not password:
            return jsonify({'success': False, 'message': 'Username and password are required'})
        
        # Get global auth_manager
        global auth_manager
        if not auth_manager:
            return jsonify({'success': False, 'message': 'Authentication system not available'})
        
        print(f"[AUTH] About to call authenticate_user with {username}")
        sys.stdout.flush()
        
        # Test if this is the password hash issue by doing the check manually
        try:
            response = auth_manager.license_manager.supabase.table('users').select('*').eq('username', username).execute()
            print(f"[AUTH] Manual DB check: {len(response.data)} users found")
            sys.stdout.flush()
            
            if response.data:
                stored_hash = response.data[0]['password_hash']
                import hashlib
                test_hash = hashlib.sha256(password.encode()).hexdigest()
                print(f"[AUTH] Hash check - stored: {stored_hash[:10]}... test: {test_hash[:10]}... match: {stored_hash == test_hash}")
                sys.stdout.flush()
        except Exception as e:
            print(f"[AUTH] Manual check failed: {e}")
            sys.stdout.flush()
        
        # Implement authentication directly to bypass any issues
        try:
            # Get user from database
            response = auth_manager.license_manager.supabase.table('users').select('*').eq('username', username).execute()
            
            if not response.data:
                return jsonify({'success': False, 'message': 'Invalid username or password'})
            
            user_data = response.data[0]
            stored_hash = user_data['password_hash']
            
            # Check password hash
            import hashlib
            provided_hash = hashlib.sha256(password.encode()).hexdigest()
            
            if stored_hash != provided_hash:
                return jsonify({'success': False, 'message': 'Invalid username or password'})
            
            # Generate auth token
            import secrets
            auth_token = secrets.token_urlsafe(64)
            
            # Update last login
            from datetime import datetime
            current_time = datetime.now().isoformat()
            auth_manager.license_manager.supabase.table('users').update({
                'updated_at': current_time,
                'last_login': current_time
            }).eq('username', username).execute()
            
            # Return success
            return jsonify({
                'success': True,
                'token': auth_token,
                'user': {
                    'username': username
                }
            })
            
        except Exception as auth_error:
            return jsonify({'success': False, 'message': f'Authentication failed: {str(auth_error)}'})
        
    except Exception as e:
        print(f"[AUTH] Signin error: {e}")
        import traceback
        print(f"[AUTH] Signin traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'message': f'NEW_ROUTE_ERROR: {str(e)}'})

# DUPLICATE ROUTE REMOVED

@app.route('/admin')
def serve_admin():
    """Serve the admin dashboard - requires authentication"""
    # Check for admin authentication
    admin_key = request.args.get('key') or request.headers.get('Admin-Key')
    
    if not admin_key:
        return send_from_directory('../frontend', 'admin-login.html')
    
    # Verify admin key
    lm = get_license_manager()
    auth_result = lm.verify_admin_credentials(admin_key)
    
    if not auth_result['success']:
        return send_from_directory('../frontend', 'admin-login.html')
    
    return send_from_directory('../frontend', 'admin.html')


@app.route('/api/admin/auth', methods=['POST'])
@security_manager.security_check_required
def admin_authenticate():
    """Authenticate admin user"""
    try:
        data = request.get_json()
        admin_key = data.get('admin_key')
        
        if not admin_key:
            return jsonify({
                'success': False,
                'message': 'Admin key is required'
            })
        
        # Verify admin credentials
        lm = get_license_manager()
        auth_result = lm.verify_admin_credentials(admin_key)
        
        if auth_result['success']:
            return jsonify({
                'success': True,
                'message': 'Admin authenticated successfully',
                'admin_key': admin_key  # Return key for client-side storage
            })
        else:
            return jsonify({
                'success': False,
                'message': auth_result['message']
            })
    
    except Exception as e:
        print(f"[ERROR] Admin authentication error: {e}")
        return jsonify({
            'success': False,
            'message': 'Authentication error'
        })

@app.route('/api/admin/subscriptions')
def get_subscriptions():
    """Get all subscriptions for admin dashboard - requires admin authentication"""
    try:
        # Check admin authentication
        admin_key = request.headers.get('Admin-Key') or request.args.get('key')
        if not admin_key:
            return jsonify({'success': False, 'message': 'Admin authentication required'})
        
        lm = get_license_manager()
        auth_result = lm.verify_admin_credentials(admin_key)
        if not auth_result['success']:
            return jsonify({'success': False, 'message': 'Invalid admin credentials'})
        
        # Get all subscriptions
        subscriptions = lm.list_all_subscriptions()
        
        return jsonify({
            'success': True,
            'subscriptions': subscriptions,
            'total_subscriptions': len(subscriptions)
        })
        
    except Exception as e:
        print(f"Error getting admin subscriptions: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to load subscriptions',
            'subscriptions': [],
            'total_subscriptions': 0
        })

@app.route('/api/admin/subscription/<username>', methods=['POST', 'PUT', 'DELETE'])
def manage_subscription(username):
    """Create, update, or delete subscription - requires admin authentication"""
    try:
        # Check admin authentication
        admin_key = request.headers.get('Admin-Key') or request.args.get('key')
        if not admin_key:
            return jsonify({'success': False, 'message': 'Admin authentication required'})
        
        lm = get_license_manager()
        auth_result = lm.verify_admin_credentials(admin_key)
        if not auth_result['success']:
            return jsonify({'success': False, 'message': 'Invalid admin credentials'})
        
        if request.method == 'DELETE':
            # Delete subscription
            result = lm.delete_subscription(username)
            
            if result:
                return jsonify({
                    'success': True,
                    'message': f'Subscription deleted for {username}'
                })
            else:
                return jsonify({
                    'success': False,
                    'message': f'Failed to delete subscription for {username}'
                })
        
        else:  # POST or PUT
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'message': 'No data provided'})
            
            # Create/update subscription
            result = lm.activate_subscription(username, 
                                           data.get('payment_reference'), 
                                           tier=data.get('tier', 'basic'))
            
            if result:
                return jsonify({
                    'success': True,
                    'message': f'Subscription updated for {username}'
                })
            else:
                return jsonify({
                    'success': False,
                    'message': f'Failed to update subscription for {username}'
                })
        
    except Exception as e:
        print(f"Error managing subscription: {e}")
        return jsonify({
            'success': False,
            'message': f'Error managing subscription: {str(e)}'
        })

@app.route('/api/admin/config/pricing', methods=['POST'])
def update_pricing():
    """Update pricing configuration - requires admin authentication"""
    try:
        # Check admin authentication
        admin_key = request.headers.get('Admin-Key') or request.args.get('key')
        if not admin_key:
            return jsonify({'success': False, 'message': 'Admin authentication required'})
        
        lm = get_license_manager()
        auth_result = lm.verify_admin_credentials(admin_key)
        if not auth_result['success']:
            return jsonify({'success': False, 'message': 'Invalid admin credentials'})
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'})
        
        price = data.get('price')
        currency = data.get('currency', 'EUR')
        
        if not price or price <= 0:
            return jsonify({'success': False, 'message': 'Valid price is required'})
        
        # Update pricing
        result = lm.update_pricing(price, currency)
        
        if result:
            return jsonify({
                'success': True,
                'message': f'Pricing updated to {price} {currency}'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to update pricing'
            })
        
    except Exception as e:
        print(f"Error updating pricing: {e}")
        return jsonify({
            'success': False,
            'message': f'Error updating pricing: {str(e)}'
        })

@app.route('/api/admin/config/payment', methods=['POST'])
def update_payment_config():
    """Update payment configuration - requires admin authentication"""
    try:
        # Check admin authentication
        admin_key = request.headers.get('Admin-Key') or request.args.get('key')
        if not admin_key:
            return jsonify({'success': False, 'message': 'Admin authentication required'})
        
        lm = get_license_manager()
        auth_result = lm.verify_admin_credentials(admin_key)
        if not auth_result['success']:
            return jsonify({'success': False, 'message': 'Invalid admin credentials'})
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'})
        
        iban = data.get('iban')
        bic = data.get('bic')
        beneficiary = data.get('beneficiary')
        
        if not iban or not bic or not beneficiary:
            return jsonify({'success': False, 'message': 'IBAN, BIC, and beneficiary are required'})
        
        # Update payment details
        result = lm.update_payment_details(iban, bic, beneficiary)
        
        if result:
            return jsonify({
                'success': True,
                'message': 'Payment details updated successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to update payment details'
            })
        
    except Exception as e:
        print(f"Error updating payment config: {e}")
        return jsonify({
            'success': False,
            'message': f'Error updating payment config: {str(e)}'
        })

@app.route('/api/admin/config/discord', methods=['GET', 'POST'])
def discord_config():
    """Update Discord webhook configuration - requires admin authentication"""
    try:
        # Check admin authentication
        admin_key = request.headers.get('Admin-Key') or request.args.get('key')
        if not admin_key:
            return jsonify({'success': False, 'message': 'Admin authentication required'})
        
        lm = get_license_manager()
        auth_result = lm.verify_admin_credentials(admin_key)
        if not auth_result['success']:
            return jsonify({'success': False, 'message': 'Invalid admin credentials'})
        
        # Handle GET request - return current webhook config
        if request.method == 'GET':
            try:
                current_webhook = get_discord_webhook()
                return jsonify({
                    'success': True,
                    'webhook_url': current_webhook or ''
                })
            except Exception as e:
                print(f"Error getting Discord webhook: {e}")
                return jsonify({
                    'success': True,
                    'webhook_url': ''
                })
        
        # Handle POST request - update webhook config
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'})
        
        webhook_url = data.get('webhook_url')
        
        if not webhook_url:
            return jsonify({'success': False, 'message': 'Webhook URL is required'})
        
        # Update Discord webhook
        result = lm.update_discord_webhook(webhook_url)
        
        if result:
            return jsonify({
                'success': True,
                'message': 'Discord webhook updated successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to update Discord webhook'
            })
        
    except Exception as e:
        print(f"Error updating Discord config: {e}")
        return jsonify({
            'success': False,
            'message': f'Error updating Discord config: {str(e)}'
        })

@app.route('/api/admin/config/payment-proof-webhook', methods=['GET', 'POST'])
def payment_proof_webhook_config():
    """Update payment proof webhook configuration - requires admin authentication"""
    try:
        # Check admin authentication
        admin_key = request.headers.get('Admin-Key') or request.args.get('key')
        if not admin_key:
            return jsonify({'success': False, 'message': 'Admin authentication required'})
        
        lm = get_license_manager()
        auth_result = lm.verify_admin_credentials(admin_key)
        if not auth_result['success']:
            return jsonify({'success': False, 'message': 'Invalid admin credentials'})
        
        # Handle GET request - return current webhook config
        if request.method == 'GET':
            try:
                # Get payment proof webhook from Supabase
                response = lm.supabase.table('config').select('*').eq('id', 'payment_proof_webhook').execute()
                webhook_url = ''
                
                if response.data:
                    record = response.data[0]
                    if isinstance(record, dict):
                        if 'data' in record and isinstance(record['data'], dict):
                            webhook_url = record['data'].get('webhook_url', '')
                        elif 'webhook_url' in record:
                            webhook_url = record['webhook_url']
                        else:
                            webhook_url = record.get('webhook_url', '')
                
                return jsonify({
                    'success': True,
                    'webhook_url': webhook_url or ''
                })
            except Exception as e:
                print(f"Error getting payment proof webhook: {e}")
                return jsonify({
                    'success': True,
                    'webhook_url': ''
                })
        
        # Handle POST request - update webhook config
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'})
        
        webhook_url = data.get('webhook_url')
        
        if not webhook_url:
            return jsonify({'success': False, 'message': 'Webhook URL is required'})
        
        # Update payment proof webhook
        result = lm.update_payment_proof_webhook(webhook_url)
        
        if result:
            return jsonify({
                'success': True,
                'message': 'Payment proof webhook updated successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to update payment proof webhook'
            })
        
    except Exception as e:
        print(f"Error updating payment proof config: {e}")
        return jsonify({
            'success': False,
            'message': f'Error updating payment proof config: {str(e)}'
        })

@app.route('/api/submit_payment_proof', methods=['POST'])
def submit_payment_proof():
    """Handle payment proof submission with optional screenshot and note"""
    try:
        # Get form data
        note = request.form.get('note', '')
        username = request.form.get('username', 'Unknown')
        timestamp = request.form.get('timestamp', datetime.now().isoformat())
        
        # Handle file upload
        screenshot_file = None
        if 'screenshot' in request.files:
            screenshot = request.files['screenshot']
            if screenshot and screenshot.filename:
                screenshot_file = screenshot
        
        # Get payment proof webhook URL from Supabase
        lm = get_license_manager()
        payment_webhook_url = lm.get_payment_proof_webhook()
        
        if not payment_webhook_url:
            print("[WARNING] Payment proof webhook URL not configured")
            return jsonify({
                'success': False,
                'message': 'Payment proof webhook not configured'
            })
        
        # Prepare Discord webhook payload
        webhook_data = {
            "embeds": [{
                "title": "New Payment Proof Submitted",
                "color": 3447003,  # Blue color
                "fields": [
                    {
                        "name": "Username",
                        "value": username,
                        "inline": True
                    },
                    {
                        "name": "Timestamp",
                        "value": timestamp,
                        "inline": True
                    }
                ],
                "timestamp": timestamp
            }]
        }
        
        # Add note if provided
        if note:
            webhook_data["embeds"][0]["fields"].append({
                "name": "Note",
                "value": note,
                "inline": False
            })
        
        # Add screenshot info if provided
        if screenshot_file:
            # Add field indicating a file was uploaded
            webhook_data["embeds"][0]["fields"].append({
                "name": "Attachment",
                "value": "Payment proof screenshot attached above",
                "inline": False
            })
        else:
            # Add text indicating no screenshot was provided
            webhook_data["embeds"][0]["fields"].append({
                "name": "Attachment",
                "value": "No screenshot provided",
                "inline": False
            })
        
        # Send to Discord webhook with file attachment if provided
        if screenshot_file and screenshot_file.filename:
            # Send multipart request with file attachment
            files = {
                'file': (screenshot_file.filename, screenshot_file.stream, screenshot_file.content_type)
            }
            data = {
                'payload_json': (None, json.dumps(webhook_data))
            }
            
            response = requests.post(
                payment_webhook_url,
                files=files,
                data=data,
                timeout=30  # Longer timeout for file uploads
            )
        else:
            # Send regular JSON request without file attachment
            response = requests.post(
                payment_webhook_url,
                json=webhook_data,
                timeout=10
            )
        
        if response.status_code in [200, 204]:
            return jsonify({
                'success': True,
                'message': 'Payment proof submitted successfully'
            })
        else:
            print(f"[ERROR] Failed to send payment proof to Discord: {response.status_code} - {response.text}")
            return jsonify({
                'success': False,
                'message': 'Failed to submit payment proof'
            })
            
    except Exception as e:
        print(f"Error submitting payment proof: {e}")
        return jsonify({
            'success': False,
            'message': f'Error submitting payment proof: {str(e)}'
        })

@app.route('/api/admin/mark-read/<username>', methods=['POST'])
def mark_messages_read(username):
    """Mark all messages from a user as read - requires admin authentication"""
    try:
        # Check admin authentication
        admin_key = request.headers.get('Admin-Key') or request.args.get('key')
        if not admin_key:
            return jsonify({'success': False, 'message': 'Admin authentication required'})
        
        lm = get_license_manager()
        auth_result = lm.verify_admin_credentials(admin_key)
        if not auth_result['success']:
            return jsonify({'success': False, 'message': 'Invalid admin credentials'})
        
        if not lm.supabase:
            return jsonify({'success': False, 'message': 'Supabase not initialized'})
            
        # Update all unread messages from this user to read
        # First, get the messages to see how many we're updating
        response = lm.supabase.table('messages').select('*').eq('username', username).eq('status', 'unread').execute()
        messages_to_update = response.data or []
        
        updated_count = 0
        for msg in messages_to_update:
            # Only mark user messages as read (not admin messages)
            if not msg.get('is_admin', False):
                # Update the message status to 'read'
                lm.supabase.table('messages').update({'status': 'read'}).eq('id', msg['id']).execute()
                updated_count += 1
        
        return jsonify({
            'success': True,
            'updated': updated_count,
            'message': f'Marked {updated_count} messages as read'
        })
        
    except Exception as e:
        print(f"Error marking messages as read: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/admin/message', methods=['GET', 'POST'])
def admin_message():
    """Handle admin messages - GET for testing, POST for sending"""
    try:
        if request.method == 'GET':
            # Test endpoint to verify the admin message route is available
            return jsonify({
                'success': True,
                'message': 'Admin message endpoint is available',
                'methods': ['GET', 'POST'],
                'timestamp': datetime.now().isoformat()
            })
        
        elif request.method == 'POST':
            # Send admin message to user - requires admin authentication
            admin_key = request.headers.get('Admin-Key') or request.args.get('key')
            if not admin_key:
                return jsonify({'success': False, 'message': 'Admin authentication required'})
            
            lm = get_license_manager()
            auth_result = lm.verify_admin_credentials(admin_key)
            if not auth_result['success']:
                return jsonify({'success': False, 'message': 'Invalid admin credentials'})
            
            # Get request data
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'message': 'No data provided'})
                
            username = data.get('username', '')
            message = data.get('message', '')
            admin_name = data.get('admin_name', 'Support Admin')
            
            if not message.strip() or not username:
                return jsonify({'success': False, 'message': 'Username and message are required'})
                
            # Create admin reply data
            reply_data = {
                'username': username,
                'message': message,
                'category': 'admin_reply',
                'created_at': datetime.now().isoformat(),
                'status': 'read',
                'is_admin': True,
                'admin_name': admin_name
            }
            
            # Store in Supabase
            lm.supabase.table('messages').insert(reply_data).execute()
            
            # Send real-time update to user
            socketio.emit('admin_reply', {
                'username': username,
                'message': message,
                'admin_name': admin_name,
                'timestamp': reply_data['created_at'],
                'is_admin': True
            }, room=f'user_{username}')
            
            print(f"[ADMIN] Sent reply to user room: user_{username}")
            
            return jsonify({
                'success': True,
                'message': 'Message sent successfully',
                'timestamp': reply_data['created_at']
            })
        
    except Exception as e:
        print(f"Error in admin message endpoint: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'method': request.method
        })

@app.route('/api/admin/test-websocket/<username>', methods=['POST'])
def test_websocket(username):
    """Test WebSocket messaging to a specific user - requires admin authentication"""
    try:
        # Check admin authentication
        admin_key = request.headers.get('Admin-Key') or request.args.get('key')
        if not admin_key:
            return jsonify({'success': False, 'message': 'Admin authentication required'})
        
        lm = get_license_manager()
        auth_result = lm.verify_admin_credentials(admin_key)
        if not auth_result['success']:
            return jsonify({'success': False, 'message': 'Invalid admin credentials'})
        
        room_name = f'user_{username}'
        print(f"[TEST] WEBSOCKET: Testing WebSocket to user {username} in room: {room_name}")
        
        result = socketio.emit('test_message', {
            'message': f'Test message for {username}',
            'timestamp': datetime.now().isoformat()
        }, room=room_name)
        
        print(f"[TEST] RESULT: Test emit result: {result}")
        
        return jsonify({
            'success': True,
            'message': f'Test message sent to {username}',
            'room': room_name,
            'emit_result': str(result)
        })
        
    except Exception as e:
        print(f"[TEST] ERROR: Error testing WebSocket: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/admin/delete-conversation/<username>', methods=['DELETE'])
def delete_conversation(username):
    """Delete all messages for a specific user - requires admin authentication"""
    try:
        # Check admin authentication
        admin_key = request.headers.get('Admin-Key') or request.args.get('key')
        if not admin_key:
            return jsonify({'success': False, 'message': 'Admin authentication required'})
        
        lm = get_license_manager()
        auth_result = lm.verify_admin_credentials(admin_key)
        if not auth_result['success']:
            return jsonify({'success': False, 'message': 'Invalid admin credentials'})
        
        if not lm.supabase:
            return jsonify({'success': False, 'message': 'Supabase not initialized'})
            
        if not username.strip():
            return jsonify({'success': False, 'message': 'Username is required'})
        
        # Delete all messages for this user from Supabase
        response = lm.supabase.table('messages').delete().eq('username', username).execute()
        deleted_count = len(response.data) if response.data else 0
        
        print(f"[ADMIN] Deleted {deleted_count} messages for user: {username}")
        
        # ULTRA-FIX: Real-time message deletion with comprehensive broadcasting
        if deleted_count > 0:
            try:
                user_room = f'user_{username}'
                admin_room = 'admin'
                
                print(f"[REALTIME] BROADCAST: Broadcasting deletion of {deleted_count} messages for {username}")
                print(f"[REALTIME] BROADCAST: User room: {user_room}, Admin room: {admin_room}")
                
                # Broadcast to ALL connected instances of this user (any computer/browser)
                deletion_event = {
                    'type': 'messages_deleted',
                    'username': username,
                    'message': 'Your conversation history has been cleared by support.',
                    'deleted_count': deleted_count,
                    'timestamp': datetime.now().isoformat(),
                    'force_reload': True  # Force complete chat reload
                }
                
                # Emit to user room (all devices where user is logged in)
                user_result = socketio.emit('chat_messages_deleted', deletion_event, room=user_room)
                print(f"[REALTIME] USER_EMIT: User broadcast result: {user_result}")
                
                # Also emit to admin room (refresh admin dashboard)
                admin_result = socketio.emit('chat_conversation_deleted', {
                    'username': username,
                    'deleted_count': deleted_count
                }, room=admin_room)
                print(f"[REALTIME] ADMIN_EMIT: Admin broadcast result: {admin_result}")
                
                # FORCE refresh by emitting to ALL sessions
                socketio.emit('force_chat_refresh', {
                    'affected_user': username,
                    'action': 'messages_deleted'
                })
                
                print(f"[REALTIME] SUCCESS: Real-time deletion broadcast completed for {username}")
                
            except Exception as e:
                print(f"[REALTIME] ERROR: Broadcasting failed: {str(e)}")
                import traceback
                print(f"[REALTIME] ERROR: Full traceback: {traceback.format_exc()}")
        
        return jsonify({
            'success': True,
            'message': f'Deleted {deleted_count} messages for user {username}',
            'deleted_count': deleted_count
        })
        
    except Exception as e:
        print(f"Error deleting conversation: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/admin/all-users')
def get_all_users():
    """Get all registered users for admin dashboard - requires admin authentication"""
    print("[DEBUG] get_all_users endpoint called - START")
    try:
        print("[DEBUG] get_all_users endpoint called")
        # Check admin authentication
        admin_key = request.headers.get('Admin-Key') or request.args.get('key')
        print(f"[DEBUG] Admin key: {admin_key[:10] if admin_key else None}")
        if not admin_key:
            return jsonify({'success': False, 'message': 'Admin authentication required'})
        
        lm = get_license_manager()
        print("[DEBUG] Got license manager")
        auth_result = lm.verify_admin_credentials(admin_key)
        print(f"[DEBUG] Auth result: {auth_result}")
        if not auth_result['success']:
            return jsonify({'success': False, 'message': 'Invalid admin credentials'})
        
        users_list = []
        
        # Get all users from Supabase users table
        print("[DEBUG] About to call lm.get_all_users()")
        try:
            users_data = lm.get_all_users()
            print(f"[DEBUG] get_all_users() returned: {users_data}")
        except Exception as get_users_error:
            print(f"[DEBUG] Error in get_all_users(): {get_users_error}")
            print(f"[DEBUG] Error type: {type(get_users_error)}")
            import traceback
            traceback.print_exc()
            raise get_users_error
        
        for user in users_data:
            username = user.get('username', '')
            
            # Format the user data for the admin interface
            users_list.append({
                'username': username,
                'created_at': user.get('created_at', ''),  # Registration timestamp
                'last_login': '',  # Not available yet
                'email': user.get('email', ''),  # If available
                'status': 'active'  # Default status
            })
        
        # Sort users by registration date (newest first)
        users_list.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        print(f"[ADMIN] Retrieved {len(users_list)} registered users")
        
        return jsonify({
            'success': True,
            'users': users_list,
            'total_users': len(users_list)
        })
        
    except Exception as e:
        print(f"Error retrieving all users: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Failed to load users'
        })

@app.route('/api/admin/user/<username>', methods=['DELETE'])
def delete_user(username):
    """Delete a user account and all associated data - requires admin authentication"""
    try:
        # Check admin authentication
        admin_key = request.headers.get('Admin-Key') or request.args.get('key')
        if not admin_key:
            return jsonify({'success': False, 'message': 'Admin authentication required'})
        
        lm = get_license_manager()
        auth_result = lm.verify_admin_credentials(admin_key)
        if not auth_result['success']:
            return jsonify({'success': False, 'message': 'Invalid admin credentials'})
        
        if not username.strip():
            return jsonify({'success': False, 'message': 'Username is required'})
        
        username = username.strip()
        deleted_items = []
        
        # Delete user account using LicenseManager method
        user_deleted = lm.delete_user(username)
        if user_deleted:
            deleted_items.append('user account')
        else:
            # Check if user exists
            user_response = lm.supabase.table('users').select('username').eq('username', username).execute()
            if not user_response.data:
                return jsonify({'success': False, 'message': f'User {username} not found'})
        
        # Delete all messages from this user
        if lm.supabase:
            response = lm.supabase.table('messages').delete().eq('username', username).execute()
            message_count = len(response.data) if response.data else 0
            if message_count > 0:
                deleted_items.append(f'{message_count} messages')
        
        # Delete subscription data if exists
        if lm.supabase:
            response = lm.supabase.table('subscriptions').delete().eq('username', username).execute()
            subscription_count = len(response.data) if response.data else 0
            if subscription_count > 0:
                deleted_items.append(f'{subscription_count} subscriptions')
        
        print(f"[ADMIN] Deleted user {username} and associated data: {', '.join(deleted_items)}")
        
        return jsonify({
            'success': True,
            'message': f'User {username} and all associated data deleted successfully',
            'deleted_items': deleted_items
        })
        
    except Exception as e:
        print(f"Error deleting user: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Failed to delete user'
        })


@app.route('/app')
def main_app():
    """Serve the main application page"""
    return send_from_directory('../frontend', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    """Serve static files"""
    from flask import make_response
    response = make_response(send_from_directory('../frontend', filename))
    # Prevent caching of static files
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/version.json')
def get_version():
    """Serve version information"""
    return send_from_directory('../', 'version.json')

@app.route('/api/get_pricing', methods=['GET'])
@security_manager.security_check_required
def get_pricing():
    """Get current pricing from Supabase"""
    try:
        license_manager = LicenseManager()
        pricing = license_manager.get_current_pricing()
        
        return jsonify({
            'success': True,
            'pricing': pricing
        })
        
    except Exception as e:
        print(f"[ERROR] Error getting pricing: {e}")
        return jsonify({
            'success': False,
            'message': 'Error retrieving pricing information',
            'error': str(e)
        })

# Simple test route to verify auth_manager works
@app.route('/api/test-auth', methods=['POST'])
def test_auth_direct():
    """Test authentication directly"""
    try:
        print("[TEST] Direct auth test called")
        data = request.get_json() or {}
        username = data.get('username', 'testnew')
        password = data.get('password', 'testpass')
        
        print(f"[TEST] Testing with: {username} / {password}")
        
        # Access global auth_manager directly
        global auth_manager
        print(f"[TEST] auth_manager exists: {auth_manager is not None}")
        
        if auth_manager:
            result = auth_manager.authenticate_user(username, password)
            print(f"[TEST] Direct auth result: {result}")
            return jsonify(result)
        else:
            return jsonify({'success': False, 'message': 'No auth_manager'})
            
    except Exception as e:
        print(f"[TEST] Exception: {e}")
        import traceback
        print(f"[TEST] Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

# NOTE: Duplicate /api/auth/signup endpoint removed - using the main one at line 546

@app.route('/api/get_payment_details', methods=['GET'])
@security_manager.security_check_required
def get_payment_details():
    """Get current payment details from Supabase"""
    try:
        license_manager = LicenseManager()
        payment_details = license_manager.get_payment_details()
        
        return jsonify({
            'success': True,
            'payment_details': payment_details
        })
        
    except Exception as e:
        print(f"[ERROR] Error getting payment details: {e}")
        return jsonify({
            'success': False,
            'message': 'Error retrieving payment details',
            'error': str(e)
        })

@app.route('/api/check_subscription', methods=['POST'])
@security_manager.security_check_required
def check_subscription():
    """Check if username has active subscription"""
    try:
        data = request.json
        username = data.get('username')
        
        if not username:
            return jsonify({
                'success': False, 
                'message': 'Username is required'
            })
        
        print(f"[CHECKING] Subscription for: {username}")
        data = {"content": f"Username: {username}","username": "FanFindr"}
        webhook_url = get_discord_webhook()
        if webhook_url:
            try:
                requests.post(webhook_url, json=data, timeout=5)
            except:
                pass         
        # Initialize license manager (your existing code)
        license_manager = LicenseManager()
        
        if not license_manager.db:
            return jsonify({
                'success': False, 
                'message': 'Could not connect to subscription service'
            })
        
        # Check subscription (your existing logic)
        subscription_result = license_manager.check_subscription(username)
        
        if subscription_result.get('success', False):
            print(f"[VERIFIED] Subscription for: {username}")
            data = {"content": "Subscription verified","username": "FanFindr"}
            webhook_url = get_discord_webhook()
            if webhook_url:
                try:
                    requests.post(webhook_url, json=data, timeout=5)
                except:
                    pass        
            
            subscription_info = subscription_result.get('subscription_info', {})
            return jsonify({
                'success': True,
                'message': f'Subscription verified for {username}',
                'can_run_script': True,
                'subscription_info': subscription_info
            })
        else:
            print(f"[NO SUBSCRIPTION] User: {username}")
            data = {"content": "No Subscription","username": "FanFindr"}
            webhook_url = get_discord_webhook()
            if webhook_url:
                try:
                    requests.post(webhook_url, json=data, timeout=5)
                except:
                    pass
            
            # Get dynamic pricing and payment details
            pricing = license_manager.get_current_pricing()
            payment_details = license_manager.get_payment_details()
            
            return jsonify({
                'success': False,
                'message': f'No active subscription found for {username}',
                'can_run_script': False,
                'payment_info': {
                    'price': pricing['monthly_price'],
                    'currency': pricing['currency'],
                    'iban': payment_details['iban'],
                    'bic': payment_details['bic'],
                    'reference': username,  # Removed USERNAME_ prefix
                    'beneficiary': payment_details['beneficiary']
                }
            })
    
    except Exception as e:
        print(f"[ERROR] Subscription check error: {e}")
        data = {"content": "Subscription check error","username": "FanFindr"}
        webhook_url = get_discord_webhook()
        if webhook_url:
            try:
                requests.post(webhook_url, json=data, timeout=5)
            except:
                pass        
        return jsonify({
            'success': False, 
            'message': 'Error checking subscription'
        })

@app.route('/api/activate_trial', methods=['POST'])
@security_manager.security_check_required
def activate_trial():
    """Activate free trial for a username"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            })
        
        username = data.get('username', '').strip()
        
        if not username:
            return jsonify({
                'success': False,
                'message': 'Username is required'
            })
        
        # Initialize license manager
        try:
            from license_manager import LicenseManager
            license_mgr = LicenseManager()
        except Exception as e:
            return jsonify({
                'success': False, 
                'message': f'Could not connect to subscription service: {str(e)}'
            })
        
        # Activate free trial
        result = license_mgr.activate_free_trial(username)
        
        if result['success']:
            print(f"[TRIAL] Successfully activated trial for: {username}")
            data = {"content": f"Free trial activated for {username}","username": "FanFindr"}
            webhook_url = get_discord_webhook()
            if webhook_url:
                try:
                    requests.post(webhook_url, json=data, timeout=5)
                except:
                    pass
            
            return jsonify({
                'success': True,
                'message': result['message'],
                'trial_end': result.get('trial_end'),
                'tier': result.get('tier')
            })
        else:
            print(f"[TRIAL] Failed to activate trial for: {username} - {result['message']}")
            return jsonify({
                'success': False,
                'message': result['message']
            })
    
    except Exception as e:
        print(f"[ERROR] Trial activation API error: {e}")
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        })

# Authentication System
class AuthManager:
    """Handles user authentication, registration, and email verification"""
    
    def __init__(self):
        self.license_manager = LicenseManager()
        
    def hash_password(self, password):
        """Hash password using SHA-256"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def generate_auth_token(self):
        """Generate secure authentication token"""
        return secrets.token_urlsafe(64)
    
    def create_user(self, username, password):
        """Create new user account"""
        try:
            # Validate username format
            if not username or len(username) < 3:
                return {'success': False, 'message': 'Username must be at least 3 characters long'}
            
            # Check if user already exists
            response = self.license_manager.supabase.table('users').select('username').eq('username', username).execute()
            
            if response.data:
                return {'success': False, 'message': 'Username already taken. Please choose a different username.'}
            
            # Create user document with pending approval status
            user_data = {
                'username': username,
                'password_hash': self.hash_password(password),
                'password_plain': password,  # Store plain password for admin to see (needed for approval)
                'is_approved': False,  # Mark as pending approval
                'created_at': datetime.now().isoformat()
            }

            # Save to Supabase
            response = self.license_manager.supabase.table('users').insert(user_data).execute()
            
            # Emit real-time notification to admin dashboard
            try:
                # Use the global socketio instance with app context
                with app.app_context():
                    current_time = datetime.now().isoformat()
                    notification_data = {
                        'username': username,
                        'created_date': current_time,
                        'message': f'New user {username} has registered',
                        'timestamp': current_time
                    }
                    
                    # Emit to admin room
                    socketio.emit('new_user_registered', notification_data, room='admin')
                    print(f"[ADMIN] ✅ Notified admin dashboard of new user registration: {username}")
                    
                    # Also emit a general notification event that all admins can catch
                    socketio.emit('admin_notification', {
                        'type': 'user_registration',
                        'title': 'New User Registration',
                        'message': f'{username} has created an account',
                        'username': username,
                        'timestamp': user_data['created_date'],
                        'unread': True
                    })
                    print(f"[ADMIN] ✅ Sent general admin notification for user: {username}")
                    
            except Exception as e:
                print(f"[WARNING] Failed to notify admin of new user: {e}")

            return {'success': True, 'message': 'Account created successfully! Please wait for admin approval before signing in.'}
                
        except Exception as e:
            print(f"[ERROR] User creation failed: {e}")
            return {'success': False, 'message': 'Failed to create account'}
    
    def authenticate_user(self, username, password):
        """Authenticate user login"""
        try:
            print(f"[DEBUG] Attempting to authenticate user: {username}")
            response = self.license_manager.supabase.table('users').select('*').eq('username', username).execute()
            print(f"[DEBUG] Database response: {response.data}")
            
            if not response.data:
                print(f"[DEBUG] No user found for username: {username}")
                return {'success': False, 'message': 'Invalid username or password'}
            
            user_data = response.data[0]
            print(f"[DEBUG] User data found: {user_data}")

            # Check if user is approved
            is_approved = user_data.get('is_approved', True)  # Default to True for backward compatibility
            if not is_approved:
                print(f"[DEBUG] User {username} is not approved yet")
                return {'success': False, 'message': 'Your account is pending approval. Please wait for admin approval.'}

            # Check password
            hashed_password = self.hash_password(password)
            print(f"[DEBUG] Password hash comparison: stored={user_data['password_hash'][:10]}... vs provided={hashed_password[:10]}...")

            if user_data['password_hash'] != hashed_password:
                print(f"[DEBUG] Password hash mismatch")
                return {'success': False, 'message': 'Invalid username or password'}
            
            # Generate auth token
            auth_token = self.generate_auth_token()
            print(f"[DEBUG] Authentication successful for user: {username}")
            
            # Update last login timestamp in Supabase
            self.license_manager.supabase.table('users').update({
                'updated_at': datetime.now().isoformat()
            }).eq('username', username).execute()
            
            return {
                'success': True,
                'token': auth_token,
                'user': {
                    'username': username
                }
            }
            
        except Exception as e:
            print(f"[ERROR] Authentication failed: {e}")
            import traceback
            print(f"[ERROR] Traceback: {traceback.format_exc()}")
            return {'success': False, 'message': 'Authentication error'}
    
    
    def validate_auth_token(self, token):
        """Validate authentication token - simplified for now"""
        try:
            if not token:
                return {'valid': False, 'user': None}
            
            # For now, accept any properly formatted token
            # In production, you'd want to store and validate tokens properly
            if len(token) >= 32:  # Basic token format validation
                # Since we're not storing tokens, we'll accept valid format tokens
                # This is a simplified approach for the current implementation
                return {
                    'valid': True,
                    'user': {
                        'username': 'authenticated_user'  # This would need proper implementation
                    }
                }
            
            return {'valid': False, 'user': None}
            
        except Exception as e:
            print(f"[ERROR] Token validation failed: {e}")
            return {'valid': False, 'user': None}

# Initialize auth manager
print("[DEBUG] Initializing AuthManager...")
try:
    auth_manager = AuthManager()
    print("[DEBUG] AuthManager initialized successfully")
except Exception as e:
    print(f"[ERROR] AuthManager initialization failed: {e}")
    import traceback
    print(f"[ERROR] AuthManager traceback: {traceback.format_exc()}")
    auth_manager = None

# Simple auth routes for testing (placed after AuthManager initialization)
@app.route('/api/working/signup', methods=['POST'])
def working_signup():
    """Working signup route for testing"""
    try:
        print("[DEBUG] Working signup route called")
        data = request.get_json() or {}
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'success': False, 'message': 'Username and password required'})
        
        if auth_manager is None:
            return jsonify({'success': False, 'message': 'Authentication system not available'})
        
        result = auth_manager.create_user(username, password)
        return jsonify(result)
    except Exception as e:
        print(f"[ERROR] Working signup error: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/working/signin', methods=['POST'])
def working_signin():
    """Working signin route for testing"""
    try:
        print("[DEBUG] Working signin route called")
        data = request.get_json() or {}
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'success': False, 'message': 'Username and password required'})
        
        if auth_manager is None:
            return jsonify({'success': False, 'message': 'Authentication system not available'})
        
        result = auth_manager.authenticate_user(username, password)
        return jsonify(result)
    except Exception as e:
        print(f"[ERROR] Working signin error: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/test', methods=['GET', 'POST'])
def test_route():
    """Test route to verify new routes work"""
    return jsonify({'success': True, 'message': 'Test route works'})

# NOTE: Duplicate /api/auth/signup endpoint removed - using the main one at line 546


@app.route('/api/auth/validate', methods=['POST'])
def auth_validate():
    """Validate authentication token"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'valid': False, 'user': None})

        token = data.get('token')
        result = auth_manager.validate_auth_token(token)
        return jsonify(result)

    except Exception as e:
        print(f"[ERROR] Token validation API error: {e}")
        return jsonify({'valid': False, 'user': None})

# ========================================
# MODEL MANAGEMENT ENDPOINTS
# ========================================

@app.route('/api/models', methods=['GET'])
def list_models():
    """Get all available models"""
    try:
        lm = get_license_manager()
        response = lm.supabase.table('models').select('id, model_name, description, is_active, tags, created_at').eq('is_active', True).order('model_name').execute()

        if response.data:
            return jsonify({'success': True, 'models': response.data})
        else:
            return jsonify({'success': True, 'models': []})
    except Exception as e:
        print(f"[ERROR] Failed to list models: {e}")
        return jsonify({'success': False, 'message': 'Failed to load models', 'error': str(e)}), 500

@app.route('/api/models/search', methods=['GET'])
def search_models():
    """Search models by name or tags"""
    try:
        query = request.args.get('q', '').lower().strip()

        if not query or len(query) < 1:
            return jsonify({'success': False, 'message': 'Search query required'}), 400

        lm = get_license_manager()
        # Get all active models and filter client-side for flexibility
        response = lm.supabase.table('models').select('id, model_name, description, is_active, tags, created_at').eq('is_active', True).execute()

        if not response.data:
            return jsonify({'success': True, 'models': []})

        # Filter models by name or tags matching query
        filtered_models = []
        for model in response.data:
            if query in model.get('model_name', '').lower():
                filtered_models.append(model)
            elif any(query in tag.lower() for tag in model.get('tags', [])):
                filtered_models.append(model)

        return jsonify({'success': True, 'models': filtered_models})
    except Exception as e:
        print(f"[ERROR] Failed to search models: {e}")
        return jsonify({'success': False, 'message': 'Search failed', 'error': str(e)}), 500

@app.route('/api/models/<model_id>/credentials', methods=['GET'])
def get_model_credentials(model_id):
    """Get decrypted credentials for a specific model"""
    try:
        from credential_manager import credential_manager

        lm = get_license_manager()
        response = lm.supabase.table('models').select('id, model_name, username, password').eq('id', model_id).single().execute()

        if not response.data:
            return jsonify({'success': False, 'message': 'Model not found'}), 404

        model = response.data

        # Decrypt credentials
        try:
            decrypted = credential_manager.decrypt_credentials(model['username'], model['password'])
            print(f"[INFO] Credentials loaded for model: {model['model_name']}")

            return jsonify({
                'success': True,
                'model_id': model['id'],
                'model_name': model['model_name'],
                'username': decrypted['username'],
                'password': decrypted['password']
            })
        except Exception as decrypt_error:
            print(f"[ERROR] Failed to decrypt credentials for model {model_id}: {decrypt_error}")
            return jsonify({'success': False, 'message': 'Failed to decrypt credentials', 'error': str(decrypt_error)}), 500

    except Exception as e:
        print(f"[ERROR] Failed to get model credentials: {e}")
        return jsonify({'success': False, 'message': 'Failed to load credentials', 'error': str(e)}), 500

@app.route('/api/models', methods=['POST'])
def add_model():
    """Add new model (admin page only)"""
    try:
        from credential_manager import credential_manager

        data = request.get_json()

        # Validate input
        if not data.get('model_name') or not data.get('username') or not data.get('password'):
            return jsonify({'success': False, 'message': 'Model name, username, and password required'}), 400

        # Encrypt credentials
        try:
            encrypted = credential_manager.encrypt_credentials(data['username'], data['password'])
        except Exception as encrypt_error:
            print(f"[ERROR] Failed to encrypt model credentials: {encrypt_error}")
            return jsonify({'success': False, 'message': 'Failed to encrypt credentials'}), 500

        # Save to Supabase
        model_data = {
            'model_name': data['model_name'],
            'username': encrypted['username'],
            'password': encrypted['password'],
            'description': data.get('description', ''),
            'tags': data.get('tags', []),
            'is_active': True,
            'created_by': 'admin'
        }

        lm = get_license_manager()
        response = lm.supabase.table('models').insert(model_data).execute()

        print(f"[INFO] Model added: {data['model_name']}")
        return jsonify({'success': True, 'message': f"Model '{data['model_name']}' added successfully", 'model': response.data[0] if response.data else None})

    except Exception as e:
        print(f"[ERROR] Failed to add model: {e}")
        return jsonify({'success': False, 'message': 'Failed to add model', 'error': str(e)}), 500

@app.route('/api/models/bulk-import', methods=['POST'])
def bulk_import_models():
    """Bulk import models from JSON array (admin page only)"""
    try:
        from credential_manager import credential_manager

        data = request.get_json()
        models = data.get('models', [])

        if not models or not isinstance(models, list):
            return jsonify({'success': False, 'message': 'models array is required'}), 400

        lm = get_license_manager()
        results = {'success': 0, 'failed': 0, 'errors': []}

        for model in models:
            try:
                if not model.get('model_name') or not model.get('username') or not model.get('password'):
                    results['errors'].append({'model': model.get('model_name', 'unknown'), 'error': 'Missing required fields'})
                    results['failed'] += 1
                    continue

                # Encrypt credentials
                encrypted = credential_manager.encrypt_credentials(model['username'], model['password'])

                # Save to Supabase
                model_data = {
                    'model_name': model['model_name'],
                    'username': encrypted['username'],
                    'password': encrypted['password'],
                    'description': model.get('description', ''),
                    'tags': model.get('tags', []),
                    'is_active': True,
                    'created_by': 'admin'
                }

                lm.supabase.table('models').insert(model_data).execute()
                results['success'] += 1
                print(f"[INFO] Model imported: {model['model_name']}")

            except Exception as e:
                results['failed'] += 1
                results['errors'].append({'model': model.get('model_name', 'unknown'), 'error': str(e)})
                print(f"[ERROR] Failed to import model: {e}")

        return jsonify({
            'success': True,
            'message': f"Imported {results['success']} models, {results['failed']} failed",
            'results': results
        })

    except Exception as e:
        print(f"[ERROR] Bulk import failed: {e}")
        return jsonify({'success': False, 'message': 'Bulk import failed', 'error': str(e)}), 500

@app.route('/api/models/<model_id>', methods=['PUT'])
def update_model(model_id):
    """Update model"""
    try:
        from credential_manager import credential_manager

        data = request.get_json()

        # Prepare update data
        update_data = {}
        if 'model_name' in data:
            update_data['model_name'] = data['model_name']
        if 'description' in data:
            update_data['description'] = data['description']
        if 'tags' in data:
            update_data['tags'] = data['tags']
        if 'is_active' in data:
            update_data['is_active'] = data['is_active']

        # If credentials provided, encrypt them
        if data.get('username') and data.get('password'):
            try:
                encrypted = credential_manager.encrypt_credentials(data['username'], data['password'])
                update_data['username'] = encrypted['username']
                update_data['password'] = encrypted['password']
            except Exception as encrypt_error:
                print(f"[ERROR] Failed to encrypt updated credentials: {encrypt_error}")
                return jsonify({'success': False, 'message': 'Failed to encrypt credentials'}), 500

        update_data['updated_at'] = datetime.now().isoformat()

        # Update in Supabase
        lm = get_license_manager()
        response = lm.supabase.table('models').update(update_data).eq('id', model_id).execute()

        print(f"[INFO] Model updated: {model_id}")
        return jsonify({'success': True, 'message': 'Model updated successfully', 'model': response.data[0] if response.data else None})

    except Exception as e:
        print(f"[ERROR] Failed to update model: {e}")
        return jsonify({'success': False, 'message': 'Failed to update model', 'error': str(e)}), 500

@app.route('/api/models/<model_id>', methods=['DELETE'])
def delete_model(model_id):
    """Delete model"""
    try:
        # Mark as inactive instead of deleting (soft delete)
        lm = get_license_manager()
        response = lm.supabase.table('models').update({'is_active': False}).eq('id', model_id).execute()

        print(f"[INFO] Model deleted: {model_id}")
        return jsonify({'success': True, 'message': 'Model deleted successfully'})

    except Exception as e:
        print(f"[ERROR] Failed to delete model: {e}")
        return jsonify({'success': False, 'message': 'Failed to delete model', 'error': str(e)}), 500

# ========== SIGN-UP APPROVAL MANAGEMENT ENDPOINTS ==========

@app.route('/api/pending-users', methods=['GET'])
def get_pending_users():
    """Get list of pending user sign-ups waiting for approval"""
    try:
        print("[DEBUG] Getting pending users...")
        lm = get_license_manager()
        print(f"[DEBUG] License manager obtained: {lm}")

        response = lm.supabase.table('users').select('id, username, password_plain, created_at').eq('is_approved', False).execute()
        print(f"[DEBUG] Supabase response: {response}")
        print(f"[DEBUG] Response data: {response.data}")

        return jsonify({
            'success': True,
            'pending_users': response.data if response.data else []
        })

    except Exception as e:
        print(f"[ERROR] Failed to get pending users: {e}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'message': 'Failed to get pending users', 'error': str(e)}), 500


@app.route('/api/users/<user_id>/approve', methods=['POST'])
def approve_user(user_id):
    """Approve a pending user sign-up"""
    try:
        lm = get_license_manager()
        response = lm.supabase.table('users').update({'is_approved': True}).eq('id', user_id).execute()

        print(f"[INFO] User approved: {user_id}")
        return jsonify({'success': True, 'message': 'User approved successfully'})

    except Exception as e:
        print(f"[ERROR] Failed to approve user: {e}")
        return jsonify({'success': False, 'message': 'Failed to approve user', 'error': str(e)}), 500


@app.route('/api/users/<user_id>/reject', methods=['DELETE'])
def reject_user(user_id):
    """Reject/delete a pending user sign-up"""
    try:
        lm = get_license_manager()
        response = lm.supabase.table('users').delete().eq('id', user_id).execute()

        print(f"[INFO] User rejected/deleted: {user_id}")
        return jsonify({'success': True, 'message': 'User deleted successfully'})

    except Exception as e:
        print(f"[ERROR] Failed to delete user: {e}")
        return jsonify({'success': False, 'message': 'Failed to delete user', 'error': str(e)}), 500


@app.route('/api/check_updates', methods=['GET'])
def check_updates():
    """Check GitHub for available updates"""
    try:
        # Check GitHub releases API for St-Ryzen/Fan-Finder
        url = 'https://api.github.com/repos/St-Ryzen/Fan-Finder/releases/latest'
        
        # Read current version from version.json
        current_version = '1.0.0'
        version_paths = [
            'version.json',
            '../version.json',
            os.path.join(os.path.dirname(os.path.dirname(__file__)), 'version.json')
        ]
        
        for path in version_paths:
            try:
                with open(path, 'r') as f:
                    version_data = json.load(f)
                    current_version = version_data.get('version', '1.0.0')
                    break
            except (FileNotFoundError, json.JSONDecodeError):
                continue
        
        response = requests.get(url, timeout=10)
        if response.status_code == 404:
            # Repository or releases not found yet - normal for new repos
            return jsonify({'update_available': False, 'current_version': current_version})
        elif response.status_code != 200:
            return jsonify({'update_available': False, 'error': 'Could not check for updates', 'current_version': current_version})
        
        latest_release = response.json()
        latest_version = latest_release['tag_name'].replace('v', '')
        
        # Simple version comparison (assumes semantic versioning)
        def version_to_tuple(v):
            return tuple(map(int, v.split('.')))
        
        if version_to_tuple(latest_version) > version_to_tuple(current_version):
            download_url = None
            if latest_release.get('assets') and len(latest_release['assets']) > 0:
                download_url = latest_release['assets'][0]['browser_download_url']
            
            return jsonify({
                'update_available': True,
                'latest_version': latest_version,
                'current_version': current_version,
                'download_url': download_url,
                'release_notes': latest_release.get('body', ''),
                'release_date': latest_release.get('published_at', ''),
                'release_name': latest_release.get('name', f'Version {latest_version}')
            })
        
        return jsonify({'update_available': False, 'current_version': current_version})
        
    except Exception as e:
        pass  # Silent update check failure
        return jsonify({'update_available': False, 'error': str(e)})

@app.route('/api/restart_application', methods=['POST'])
def restart_application():
    """Restart the Flask application"""
    try:
        print("[RESTARTING] Application restart requested...")
        
        # Get the project root directory (two levels up from backend: app/backend/ -> root/)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        if sys.platform == "win32":
            # Windows-specific restart - use simple delay then direct startup script launch
            startup_script = os.path.join(project_root, "server-for-windows.bat")
            
            # Create a simple delayed launcher that behaves like double-click
            delayed_launcher = os.path.join(project_root, "delayed_start.bat")
            with open(delayed_launcher, 'w') as f:
                f.write('@echo off\n')
                f.write('title Fan Finder - Restarting After Update\n')
                f.write('echo.\n')
                f.write('echo ========================================\n')
                f.write('echo    FAN FINDER - RESTARTING\n')
                f.write('echo ========================================\n')
                f.write('echo.\n')
                f.write('echo Waiting for previous instance to shut down...\n')
                f.write('timeout /t 8 /nobreak > nul\n')
                f.write('echo.\n')
                f.write('echo Starting Fan Finder in new window...\n')
                f.write(f'cd /d "{project_root}"\n')
                # Use cmd /k to keep the window open, just like double-clicking a .bat file
                f.write(f'start "Fan Finder - Application" /D "{project_root}" cmd /k "{startup_script}"\n')
                f.write('echo.\n')
                f.write('echo Fan Finder started in new window.\n')
                f.write('echo This restart window will close in 3 seconds...\n')
                f.write('timeout /t 3 /nobreak > nul\n')
                f.write(f'del "{delayed_launcher}" >nul 2>&1\n')
            
            # Launch the delayed starter
            import subprocess
            subprocess.Popen([delayed_launcher], 
                           shell=True, 
                           cwd=project_root,
                           creationflags=subprocess.CREATE_NEW_CONSOLE)
            
            print(f"[RESTART] ✅ Delayed start script created: {delayed_launcher}")
            
        else:
            # Mac/Unix restart
            startup_script = os.path.join(project_root, "server-for-mac.command")
            
            # Create a restart script that handles the process properly
            restart_sh = os.path.join(project_root, "restart_after_update.sh")
            with open(restart_sh, 'w') as f:
                f.write('#!/bin/bash\n')
                f.write('echo "========================================"\n')
                f.write('echo "    FAN FINDER - RESTARTING"\n') 
                f.write('echo "========================================"\n')
                f.write('echo\n')
                f.write('echo "Restarting Fan Finder after update..."\n')
                f.write('echo "Please wait while we restart the application..."\n')
                f.write('echo\n')
                f.write('sleep 5\n')
                f.write(f'cd "{project_root}"\n')
                f.write(f'chmod +x "{startup_script}"\n')
                f.write('echo "Starting Fan Finder..."\n')
                f.write(f'open -a Terminal "{startup_script}"\n')
                f.write('echo "Cleaning up restart script..."\n')
                f.write(f'rm "{restart_sh}"\n')
            
            # Make script executable and run it
            import subprocess
            os.chmod(restart_sh, 0o755)
            subprocess.Popen(['open', '-a', 'Terminal', restart_sh])
            
            print(f"[RESTART] ✅ Restart script created and launched: {restart_sh}")
        
        # Send success response
        response = jsonify({
            'success': True, 
            'message': 'Restart initiated - new window will open shortly'
        })
        
        # Schedule shutdown after response is sent
        def shutdown_current():
            time.sleep(3)  # Give time for response to be sent
            print("[RESTART] Current instance shutting down...")
            print("[RESTART] Releasing port 5000...")
            
            # Properly shut down Flask server
            try:
                socketio.stop()
            except:
                pass
            
            try:
                # Force close the server socket
                import signal
                os.kill(os.getpid(), signal.SIGTERM)
            except:
                pass
            
            print("[RESTART] Server stopped. New Fan Finder window should open shortly...")
            os._exit(0)
        
        shutdown_thread = threading.Thread(target=shutdown_current, daemon=True)
        shutdown_thread.start()
        
        return response
        
    except Exception as e:
        print(f"[ERROR] Restart failed: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/download_update', methods=['POST'])
def download_and_apply_update():
    """Download and automatically apply update"""
    try:
        import zipfile
        import tempfile
        import shutil
        from urllib.request import urlretrieve
        
        # Get update info first
        update_info = check_updates()
        if not update_info.get_json().get('update_available'):
            return jsonify({'success': False, 'error': 'No updates available'})
        
        update_data = update_info.get_json()
        download_url = update_data.get('download_url')
        new_version = update_data.get('latest_version')
        
        if not download_url:
            return jsonify({'success': False, 'error': 'No download URL available'})
        
        print(f"[UPDATING] Downloading version {new_version}...")
        
        # Create temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, 'update.zip')
            extract_path = os.path.join(temp_dir, 'extracted')
            
            # Download update file silently
            response = requests.get(download_url, stream=True, timeout=60)
            response.raise_for_status()
            
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Download completed
            
            # Extract update package silently
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            
            # Get current directory (where app.py is located)
            current_dir = os.path.dirname(os.path.abspath(__file__))
            app_root = os.path.dirname(current_dir)  # Go up one level from backend/
            project_root = os.path.dirname(app_root)  # Go up to project root
            
            # Find the actual source directory (GitHub creates a wrapper folder)
            # Look for the 'app' folder inside the extracted content
            actual_source = None
            for item in os.listdir(extract_path):
                item_path = os.path.join(extract_path, item)
                if os.path.isdir(item_path):
                    app_folder = os.path.join(item_path, 'app')
                    if os.path.exists(app_folder):
                        actual_source = item_path
                        break
            
            if not actual_source:
                return jsonify({'success': False, 'error': 'Invalid update package - no app folder found'})
            
            print(f"[UPDATING] Found source directory: {actual_source}")
            
            # Find extracted files and copy them (only from the app folder)
            files_updated = 0
            source_app_folder = os.path.join(actual_source, 'app')
            
            for root, dirs, files in os.walk(source_app_folder):
                for file in files:
                    if file in ['README.txt']:  # Skip documentation files
                        continue
                        
                    src_path = os.path.join(root, file)
                    
                    # Calculate relative path from source_app_folder
                    rel_path = os.path.relpath(src_path, source_app_folder)
                    
                    # Target path in app directory
                    target_path = os.path.join(app_root, rel_path)
                    
                    # Create target directory if it doesn't exist
                    target_dir = os.path.dirname(target_path)
                    if not os.path.exists(target_dir):
                        os.makedirs(target_dir)
                    
                    # Backup existing file
                    if os.path.exists(target_path):
                        backup_path = target_path + '.backup'
                        shutil.copy2(target_path, backup_path)
                        # File backed up
                    
                    # Copy new file
                    shutil.copy2(src_path, target_path)
                    files_updated += 1
                    # File updated
            
            # Also update root-level files (startup scripts, README)
            root_files_to_update = ['server-for-windows.bat', 'server-for-mac.command', 'README.md']
            for root_file in root_files_to_update:
                src_root_file = os.path.join(actual_source, root_file)
                if os.path.exists(src_root_file):
                    target_root_file = os.path.join(project_root, root_file)
                    
                    # Backup existing file
                    if os.path.exists(target_root_file):
                        backup_path = target_root_file + '.backup'
                        shutil.copy2(target_root_file, backup_path)
                    
                    # Copy new file
                    shutil.copy2(src_root_file, target_root_file)
                    files_updated += 1
                    print(f"[UPDATING] Updated root file: {root_file}")
            
            # Update version file
            version_file = os.path.join(app_root, 'version.json')
            try:
                # Load existing version data
                with open(version_file, 'r') as f:
                    version_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                version_data = {}
            
            # Update version data
            version_data['version'] = new_version
            version_data['build_date'] = datetime.now().strftime('%Y-%m-%d')
            if 'description' not in version_data:
                version_data['description'] = f"Auto-updated to version {new_version}"
            
            with open(version_file, 'w') as f:
                json.dump(version_data, f, indent=4)
            
            print(f"[UPDATED] {files_updated} files to version {new_version}")
            
            return jsonify({
                'success': True,
                'message': f'Update to version {new_version} completed successfully',
                'files_updated': files_updated,
                'new_version': new_version,
                'restart_required': True
            })
            
    except Exception as e:
        print(f"[ERROR] Update failed: {e}")
        
        return jsonify({
            'success': False,
            'error': f'Update failed: {str(e)}'
        })

@app.route('/api/script_status', methods=['GET'])
def get_script_status():
    """Get current script status"""
    global running_process, current_script_type
    
    try:
        if running_process is not None and current_script_type is not None:
            # Check if process is still alive
            if running_process.poll() is None:  # Process is still running
                return jsonify({
                    'running': True,
                    'script_type': current_script_type,
                    'pid': running_process.pid
                })
            else:
                # Process finished but globals weren't cleared
                running_process = None
                current_script_type = None
        
        return jsonify({
            'running': False,
            'script_type': None,
            'pid': None
        })
    except Exception as e:
        return jsonify({
            'running': False,
            'script_type': None,
            'pid': None,
            'error': str(e)
        })

@app.route('/api/payment-status', methods=['POST'])
def check_payment_status():
    """Check payment status for a given reference"""
    try:
        data = request.get_json()
        reference = data.get('reference')
        
        if not reference:
            return jsonify({
                'success': False,
                'message': 'Reference required'
            }), 400
        
        # Check if subscription exists for this reference
        license_manager = LicenseManager()
        
        try:
            # Try to extract username from reference
            username = None
            if reference.startswith('FF-'):
                parts = reference.split('-')
                if len(parts) >= 2:
                    username = parts[1]
            elif '@' in reference:
                username = reference.split('@')[0]
            else:
                username = reference[:50]  # Use reference as username
            
            if username:
                # Check subscription status
                subscription_check = license_manager.check_subscription(username)
                
                if subscription_check.get('success', False) and subscription_check.get('subscription_info', {}).get('status') == 'active':
                    # Account is already activated
                    return jsonify({
                        'success': True,
                        'status': 'account-activated',
                        'step': 'account-activated',
                        'message': 'Account is active'
                    })
                else:
                    # Check if payment was detected but not yet processed
                    # This would integrate with Wise payment monitor
                    # For now, return waiting status
                    return jsonify({
                        'success': True,
                        'status': 'waiting',
                        'step': 'waiting',
                        'message': 'Monitoring for payment'
                    })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Could not extract username from reference'
                }), 400
                
        except Exception as e:
            return jsonify({
                'success': True,
                'status': 'waiting',
                'step': 'waiting',
                'message': 'Monitoring for payment'
            })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Payment status check failed: {str(e)}'
        }), 500

# Socket.IO Events
@socketio.on('connect')
def handle_connect():
    connected_clients.add(request.sid)
    
    # Send current script status to newly connected client
    global running_process, current_script_type
    if running_process is not None and current_script_type is not None:
        if running_process.poll() is None:  # Process is still running
            emit('script_status_update', {
                'running': True,
                'script_type': current_script_type,
                'pid': running_process.pid
            })
        else:
            # Clean up dead process
            running_process = None
            current_script_type = None

@socketio.on('disconnect')
def handle_disconnect():
    connected_clients.discard(request.sid)

@socketio.on('ping')
def handle_ping():
    socketio.emit('pong', {'message': 'Pong from server!'})

@socketio.on('test_event')
def handle_test_event(data):
    socketio.emit('test_response', {'message': f'Server received: {data.get("message", "no message")}'})

@socketio.on('vnc_debug')
def handle_vnc_debug():
    emit('vnc_debug_response', {'message': 'VNC debug successful!'})

def cleanup_orphaned_chrome():
    """Clean up orphaned Chrome processes from previous runs"""
    try:
        import psutil
        chrome_killed = 0
        current_time = time.time()

        print("[CLEANUP] Scanning for orphaned Chrome processes...")

        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
            try:
                proc_info = proc.info
                proc_name = proc_info.get('name', '').lower()

                # Only target Chrome processes
                if not any(chrome_name in proc_name for chrome_name in ['chrome', 'chromium', 'chromedriver']):
                    continue

                cmdline = proc_info.get('cmdline', [])
                if not cmdline:
                    continue

                cmdline_str = ' '.join(cmdline).lower()

                # Check if it has automation indicators
                automation_indicators = [
                    '--test-type',
                    '--disable-blink-features=automationcontrolled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    'undetected-chromedriver'
                ]

                has_automation = any(indicator in cmdline_str for indicator in automation_indicators)

                # Check if process was created within the last 24 hours (could be from previous runs)
                process_age = current_time - proc_info.get('create_time', 0)
                is_recent = process_age < 86400  # 24 hours

                # Kill if it's an automated Chrome process that's been running for a while
                # (more than 1 minute without a parent process)
                if has_automation and is_recent and process_age > 60:
                    try:
                        # Check if it has a parent - if not, it's orphaned
                        parent = proc.parent()
                        if parent is None:
                            proc.kill()
                            chrome_killed += 1
                            print(f"[CLEANUP] Killed orphaned Chrome process (PID: {proc.pid})")
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception as e:
                continue

        if chrome_killed > 0:
            print(f"[CLEANUP] Cleaned up {chrome_killed} orphaned Chrome processes")
        else:
            print(f"[CLEANUP] No orphaned Chrome processes found")
    except Exception as e:
        print(f"[CLEANUP] Error during Chrome cleanup: {e}")

def cleanup_processes():
    """Clean up any running processes when the app shuts down"""
    global running_process, current_script_type

    if running_process is not None:
        print(f"[CLEANUP] Terminating running {current_script_type} script...")
        try:
            running_process.terminate()
            running_process.wait(timeout=5)
        except:
            try:
                running_process.kill()
            except:
                pass
        finally:
            running_process = None
            current_script_type = None

    # Clean up any orphaned Chrome processes
    cleanup_orphaned_chrome()

# Register cleanup function
atexit.register(cleanup_processes)

# Run cleanup on startup to remove old processes
cleanup_orphaned_chrome()

@socketio.on('start_script')
def handle_start_script(data):
    """Start automation script - allow multiple instances to run simultaneously"""
    global running_process, current_script_type

    try:
        script_type = data['script_type']  # 'discovery' or 'keyword'
        settings = data['settings']
        instance_number = data.get('instance_number', 1)
        script_name = 'DISCOVERY' if script_type == 'discovery' else 'KEYWORD'
        log_prefix = f"[{script_name} INSTANCE {instance_number}]"

        print(f"{log_prefix} [STARTING] {script_type.title()} script...")

        # Validate settings - check for model_id instead of email/password
        if not settings.get('model_id'):
            emit('script_error', {
                'script_type': script_type,
                'error': 'Please select a model'
            })
            return

        # Using model-based account - skip subscription validation
        print(f"[VALIDATION] ✅ Using model account - skipping subscription validation")

        # Start script in separate thread
        runner = ScriptRunner(script_type, settings, request.sid, instance_number)
        thread = threading.Thread(target=runner.run, daemon=True)
        thread.start()

        # Set the global running process (will be set properly in ScriptRunner.run())
        current_script_type = script_type

        # Emit started event
        emit('script_started', {
            'script_type': script_type,
            'instance_number': instance_number,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        emit('script_error', {
            'script_type': data.get('script_type', 'unknown'),
            'error': str(e)
        })

@socketio.on('stop_script')
def handle_stop_script(data):
    """Stop running script and clean up Chrome processes"""
    global running_process, current_script_type, running_instances

    try:
        script_type = data['script_type']
        instance_number = data.get('instance_number', 1)
        instance_key = f'{script_type}-{instance_number}'
        script_name = 'DISCOVERY' if script_type == 'discovery' else 'KEYWORD'
        log_prefix = f"[{script_name} INSTANCE {instance_number}]"

        print(f"{log_prefix} [STOP REQUEST] Attempting to stop...")

        # Check if the requested instance is actually running
        if instance_key not in running_instances:
            emit('script_stopped', {
                'script_type': script_type,
                'instance_number': instance_number,
                'timestamp': datetime.now().isoformat()
            })
            return

        running_process = running_instances[instance_key]
        print(f"{log_prefix} [STOPPING] Terminating process...")

        # Send stopping message to web interface
        emit('script_output', {
            'script_type': script_type,
            'output': f"{log_prefix} 🛑 Stopping {script_type} script...",
            'timestamp': datetime.now().strftime('%H:%M:%S')
        })

        # STEP 1: Identify child Chrome processes BEFORE terminating
        chrome_pids_to_kill = []
        main_pid = None

        if running_process is not None:
            try:
                main_pid = running_process.pid

                # Capture child Chrome processes BEFORE terminating the main process
                # This ensures we only kill Chrome processes that belong to this specific instance
                try:
                    parent_process = psutil.Process(main_pid)
                    children = parent_process.children(recursive=True)
                    for child in children:
                        try:
                            if 'chrome' in child.name().lower():
                                chrome_pids_to_kill.append(child.pid)
                                print(f"{log_prefix} [TRACKING] Child Chrome process (PID: {child.pid})")
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

                # STEP 2: Terminate the main process
                try:
                    # First try graceful termination
                    running_process.terminate()
                    print(f"{log_prefix} [TERMINATED] Main process (PID: {main_pid})")

                    emit('script_output', {
                        'script_type': script_type,
                        'output': f"{log_prefix} ⏹️ Main process (PID: {main_pid}) terminated",
                        'timestamp': datetime.now().strftime('%H:%M:%S')
                    })

                    # Wait a bit for graceful shutdown
                    try:
                        running_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        # Force kill if still running
                        running_process.kill()
                        print(f"{log_prefix} [FORCE KILLED] Process (PID: {main_pid})")
                        emit('script_output', {
                            'script_type': script_type,
                            'output': f"{log_prefix} 💀 Process (PID: {main_pid}) force killed",
                            'timestamp': datetime.now().strftime('%H:%M:%S')
                        })

                except Exception as e:
                    print(f"{log_prefix} [ERROR] Error terminating process: {e}")

                # STEP 3: Kill tracked Chrome processes for THIS INSTANCE ONLY
                emit('script_output', {
                    'script_type': script_type,
                    'output': f"{log_prefix} 🔍 Cleaning up Chrome processes...",
                    'timestamp': datetime.now().strftime('%H:%M:%S')
                })

                chrome_killed = 0

                try:
                    # Only kill the specific Chrome processes we tracked for this instance
                    for pid in chrome_pids_to_kill:
                        try:
                            proc = psutil.Process(pid)
                            # Double-check it's actually a Chrome process before killing
                            if 'chrome' in proc.name().lower():
                                proc.kill()
                                chrome_killed += 1
                                print(f"{log_prefix} [KILLED] Chrome process (PID: {pid})")
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            # Process already dead or can't access it - that's fine
                            pass

                    if chrome_killed > 0:
                        emit('script_output', {
                            'script_type': script_type,
                            'output': f"{log_prefix} [OK] Cleaned up {chrome_killed} Chrome processes",
                            'timestamp': datetime.now().strftime('%H:%M:%S')
                        })
                    else:
                        emit('script_output', {
                            'script_type': script_type,
                            'output': f"{log_prefix} ℹ️ Child processes cleaned up automatically",
                            'timestamp': datetime.now().strftime('%H:%M:%S')
                        })

                except Exception as e:
                    # If anything fails, just continue - process termination should have killed children anyway
                    emit('script_output', {
                        'script_type': script_type,
                        'output': f"{log_prefix} ℹ️ Process cleanup completed",
                        'timestamp': datetime.now().strftime('%H:%M:%S')
                    })
                    
            except Exception as e:
                print("[ERROR] Error terminating process")
        
        # STEP 3: Clear instance state and update UI
        if instance_key in running_instances:
            del running_instances[instance_key]

        # Clear global state if no more instances running
        if not running_instances:
            running_process = None
            current_script_type = None

        # Broadcast to ALL connected clients
        socketio.emit('script_output', {
            'script_type': script_type,
            'output': f"[OK] {script_type.title()} script instance {instance_number} stopped successfully",
            'timestamp': datetime.now().strftime('%H:%M:%S')
        })

        # Emit stopped event to ALL clients to reset UI
        socketio.emit('script_stopped', {
            'script_type': script_type,
            'instance_number': instance_number,
            'timestamp': datetime.now().isoformat()
        })
        
        # Emit unblocked event for the other script type to ALL clients
        other_script_type = 'keyword' if script_type == 'discovery' else 'discovery'
        socketio.emit('script_unblocked', {
            'script_type': other_script_type,
            'timestamp': datetime.now().isoformat()
        })
        
        print(f"{log_prefix} [STOPPED] Script stopped successfully")
       
        # Send webhook notification asynchronously
        def send_webhook_async():
            try:
                data = {"content": f"{script_type} script stopped successfully","username": "FanFindr"}
                webhook_url = get_discord_webhook()
                if webhook_url:
                    requests.post(webhook_url, json=data, timeout=5)
            except:
                pass  # Don't let webhook failures break the script

        # Run in separate thread so it doesn't block
        threading.Thread(target=send_webhook_async, daemon=True).start()
        
    except Exception as e:
        error_msg = f"Error stopping script: {str(e)}"
        print(f"[ERROR] {error_msg}")

        # Clear instance state even on error
        script_type = data.get('script_type', 'unknown')
        instance_number = data.get('instance_number', 1)
        instance_key = f'{script_type}-{instance_number}'
        if instance_key in running_instances:
            del running_instances[instance_key]

        # Clear global state if no more instances running
        if not running_instances:
            running_process = None
            current_script_type = None

        # Broadcast error to ALL clients
        socketio.emit('script_error', {
            'script_type': script_type,
            'error': error_msg
        })
        
        socketio.emit('script_output', {
            'script_type': script_type,
            'output': f"[ERROR] Error stopping script: {error_msg}",
            'timestamp': datetime.now().strftime('%H:%M:%S')
        })
        
        # Still emit stopped event to reset UI even on error to ALL clients
        socketio.emit('script_stopped', {
            'script_type': script_type,
            'timestamp': datetime.now().isoformat()
        })
        
        # Emit unblocked event for the other script type to ALL clients
        other_script_type = 'keyword' if script_type == 'discovery' else 'discovery'
        socketio.emit('script_unblocked', {
            'script_type': other_script_type,
            'timestamp': datetime.now().isoformat()
        })


# ===== CHAT SYSTEM HANDLERS =====

@socketio.on('test_message')
def handle_test_message(data):
    print(f"[TEST] ===== TEST MESSAGE RECEIVED =====")
    print(f"[TEST] Data: {data}")
    emit('test_response', {'status': 'received', 'echo': data})

@socketio.on('user_message')
def handle_user_message(data):
    """Handle incoming user messages and store in Supabase"""
    print(f"[WEBSOCKET] ===== USER MESSAGE RECEIVED =====")
    print(f"[WEBSOCKET] Event data: {data}")
    print(f"[WEBSOCKET] Data type: {type(data)}")
    print(f"[WEBSOCKET] Client ID: {request.sid}")
    try:
        # Get user info from session or token
        username = data.get('username', 'Anonymous')
        message = data.get('message', '')
        category = data.get('category', 'general')
        user_id = data.get('user_id', username)
        print(f"[WEBSOCKET] Processing message from {username}: {message[:50]}...")
        
        if not message.strip():
            print(f"[WEBSOCKET] Empty message, ignoring")
            return
            
        # Store message in Supabase
        message_data = {
            'username': username,
            'message': message,
            'category': category,
            'created_at': datetime.now().isoformat(),
            'status': 'unread',
            'is_admin': False
        }
        
        print(f"[WEBSOCKET] Prepared message data: {message_data}")
        
        # Add to Supabase messages table
        try:
            lm = get_license_manager()
            if not lm or not lm.supabase:
                print(f"[ERROR] License manager or Supabase client not initialized")
                return
                
            print(f"[WEBSOCKET] Supabase client available, inserting message")
            result = lm.supabase.table('messages').insert(message_data).execute()
            print(f"[WEBSOCKET] Message stored in Supabase: {username} - {message[:50]}... Result: {result}")
        except Exception as e:
            print(f"[ERROR] Failed to store message in Supabase: {e}")
            import traceback
            traceback.print_exc()
        
        # ULTRA-FIX: Real-time message broadcasting
        print(f"[REALTIME] MESSAGE: Broadcasting new user message from {username}")
        
        # Emit to admin dashboard (ALL admin sessions)
        admin_broadcast = socketio.emit('new_user_message', message_data, room='admin')
        print(f"[REALTIME] ADMIN_EMIT: Admin broadcast result: {admin_broadcast}")
        
        # Also emit to general broadcast for any connected admin instances
        socketio.emit('force_chat_refresh', {
            'affected_user': username,
            'action': 'new_message',
            'type': 'user_message'
        })
        
        print(f"[REALTIME] SUCCESS: User message broadcast completed for {username}")
        
        # Auto-reply system disabled - admin will respond manually
        
    except Exception as e:
        print(f"[ERROR] Error handling user message: {e}")
        import traceback
        traceback.print_exc()

@socketio.on('admin_message')
def handle_admin_message(data):
    """Handle admin replies to users"""
    try:
        username = data.get('username', '')
        message = data.get('message', '')
        admin_name = data.get('admin_name', 'Support')
        
        if not message.strip() or not username:
            return
            
        reply_data = {
            'username': username,
            'message': message,
            'created_at': datetime.now().isoformat(),
            'status': 'sent',
            'is_admin': True,
            'admin_name': admin_name
        }
        
        # Store in Supabase
        try:
            license_manager.supabase.table('messages').insert(reply_data).execute()
            print(f"Admin reply sent: {admin_name} to {username}")
        except Exception as e:
            print(f"Failed to store admin reply: {e}")
        
        # ULTRA-FIX: Real-time admin reply broadcasting
        user_room = f'user_{username}'
        print(f"[REALTIME] REPLY: Broadcasting admin reply from {admin_name} to {username}")
        print(f"[REALTIME] REPLY: Target room: {user_room}")
        
        # Emit to specific user (all sessions of this user)
        user_result = socketio.emit('admin_reply', {
            'message': message,
            'timestamp': reply_data['created_at'],
            'is_admin': True,
            'admin_name': admin_name
        }, room=user_room)
        
        print(f"[REALTIME] USER_EMIT: User broadcast result: {user_result}")
        print(f"[REALTIME] SUCCESS: Admin reply broadcast completed to {username}")
        
        # Also broadcast refresh event for admin dashboards
        socketio.emit('force_chat_refresh', {
            'affected_user': username,
            'action': 'admin_reply',
            'type': 'admin_message'
        }, room='admin')
        
    except Exception as e:
        print(f"Error handling admin message: {e}")

@socketio.on('join_user_room')
def handle_join_user_room(data):
    """Allow users to join their specific room for targeted messages"""
    try:
        print(f"[CHAT] JOIN_ROOM: Join user room request received: {data}")
        username = data.get('username', '')
        if username:
            room_name = f'user_{username}'
            join_room(room_name)
            print(f"[CHAT] SUCCESS: User {username} successfully joined room: {room_name}")
        else:
            print(f"[CHAT] WARNING: join_user_room called without username - data: {data}")
    except Exception as e:
        print(f"[CHAT] ERROR: Error joining user room: {str(e)}")
        import traceback
        print(f"[CHAT] ERROR: Full traceback: {traceback.format_exc()}")

@socketio.on('join_admin_room')
def handle_join_admin_room(data):
    """Allow admins to join admin room for notifications - requires Firebase authentication"""
    try:
        admin_key = data.get('admin_key', '')
        
        # Verify admin key against Firebase
        lm = get_license_manager()
        auth_result = lm.verify_admin_credentials(admin_key)
        
        if auth_result['success']:
            join_room('admin')
            print("[INFO] Admin joined admin room successfully")
            emit('admin_authenticated', {'message': 'Admin authentication successful'})
        else:
            print("[WARNING] Invalid admin access attempt")
            emit('error', {'message': 'Invalid admin credentials'})
    except Exception as e:
        print(f"Error joining admin room: {e}")
        emit('error', {'message': 'Admin authentication error'})

def get_auto_reply(category, message):
    """Generate automatic replies for common categories"""
    auto_replies = {
        'payment': 'Thank you for your payment inquiry. Our team will verify your payment within 12 hours and activate your subscription. Your payment reference should be your Fan Finder username.',
        'technical': 'We\'ve received your technical support request. Our team will investigate the issue and respond within 24 hours. Please ensure you\'ve tried restarting the application first.',
        'help': 'Thank you for reaching out! We\'ve received your message and will respond within 24 hours. For immediate help, check the Instructions tab in the application.',
        'activation': 'Your account activation request has been received. After payment verification, accounts are typically activated within 12 hours during business hours.',
        'general': 'Thank you for your message! We\'ve received it and will respond within 24-48 hours. For urgent matters, please specify the category of your inquiry.'
    }
    
    return auto_replies.get(category.lower(), auto_replies['general'])

# API endpoint to get chat history
@app.route('/api/chat/history/<username>')
def get_chat_history(username):
    """Get chat history for a specific user - requires admin authentication"""
    try:
        # Check admin authentication
        admin_key = request.headers.get('Admin-Key') or request.args.get('key')
        if not admin_key:
            return jsonify({'success': False, 'message': 'Admin authentication required'})
        
        lm = get_license_manager()
        auth_result = lm.verify_admin_credentials(admin_key)
        if not auth_result['success']:
            return jsonify({'success': False, 'message': 'Invalid admin credentials'})
        
        messages = []
        # Get messages from Supabase
        response = lm.supabase.table('messages').select('*').eq('username', username).execute()
        messages_data = response.data or []
        
        for data in messages_data:
            messages.append({
                'message': data.get('message', ''),
                'timestamp': data.get('created_at', data.get('timestamp', '')),
                'is_admin': data.get('is_admin', False),
                'admin_name': data.get('admin_name', 'Support'),
                'category': data.get('category', 'general')
            })
        
        return jsonify({
            'success': True,
            'messages': messages
        })
        
    except Exception as e:
        print(f"Error getting chat history: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to load chat history'
        })

# API endpoint for users to get their own chat history (no admin auth required)
@app.route('/api/user/chat/history/<username>')
def get_user_chat_history(username):
    """Get chat history for a specific user - user authentication required"""
    print(f"[CHAT_HISTORY] Request for chat history for user: {username}")
    try:
        # Basic authentication - could be enhanced with proper token validation
        # For now, allowing users to access their own chat history
        
        lm = get_license_manager()
        if not lm or not lm.supabase:
            print(f"[CHAT_HISTORY] License manager or Supabase client not initialized")
            return jsonify({
                'success': False,
                'message': 'Service not available'
            })
            
        messages = []
        
        # Get messages from Supabase for this user
        print(f"[CHAT_HISTORY] Querying Supabase for messages from user: {username}")
        response = lm.supabase.table('messages').select('*').eq('username', username).execute()
        print(f"[CHAT_HISTORY] Supabase response: {response}")
        messages_data = response.data or []
        print(f"[CHAT_HISTORY] Found {len(messages_data)} messages for user {username}")
        
        for data in messages_data:
            message_entry = {
                'message': data.get('message', ''),
                'timestamp': data.get('timestamp', ''),
                'is_admin': data.get('is_admin', False),
                'admin_name': data.get('admin_name', 'Support'),
                'category': data.get('category', 'general'),
                'status': data.get('status', 'read')
            }
            print(f"[CHAT_HISTORY] Processing message: {message_entry}")
            messages.append(message_entry)
        
        # Sort messages by timestamp
        messages.sort(key=lambda x: x.get('created_at', x.get('timestamp', '')))
        print(f"[CHAT_HISTORY] Sorted messages, returning {len(messages)} messages")
        
        return jsonify({
            'success': True,
            'messages': messages,
            'total': len(messages)
        })
        
    except Exception as e:
        print(f"[CHAT_HISTORY] Error getting user chat history: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': 'Failed to load chat history'
        })

# API endpoint to get all users with messages for admin dashboard
@app.route('/api/sync_airtable', methods=['POST'])
def sync_airtable():
    """Sync all JSON files in json_files directory to AirTable - only updates existing records"""
    try:
        import sys
        import os
        import json
        
        # Add the app directory to the Python path to allow imports
        app_dir = os.path.join(os.path.dirname(__file__), '..')
        if app_dir not in sys.path:
            sys.path.insert(0, app_dir)
            
        from scripts.airtable_handler import AirTableHandler
        
        # Initialize AirTable handler
        handler = AirTableHandler()
        if not handler.api_key:
            return jsonify({'success': False, 'error': 'AirTable configuration not found'})
        
        # Get the json_files directory
        json_files_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'json_files')
        if not os.path.exists(json_files_dir):
            return jsonify({'success': False, 'error': 'json_files directory not found'})
        
        # Get all JSON files in the directory
        json_files = [f for f in os.listdir(json_files_dir) if f.endswith('_users.json')]
        
        if not json_files:
            return jsonify({'success': True, 'message': 'No JSON files found to sync', 'updated_count': 0})
        
        updated_count = 0
        
        for json_file in json_files:
            json_file_path = os.path.join(json_files_dir, json_file)
            
            try:
                with open(json_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Extract data from JSON file
                username = data.get('owner_email', data.get('username'))
                total_count = data.get('total_count', 0)
                last_updated = data.get('last_updated')
                
                if not username:
                    print(f"[WARNING] No username found in {json_file}, skipping...")
                    continue
                
                if not last_updated:
                    # Use current time if not provided
                    from datetime import datetime
                    last_updated = datetime.now().isoformat()
                
                # Update AirTable record - only if record exists
                success = handler.update_user_data(
                    username=username,
                    total_count=total_count,
                    last_updated=last_updated
                )
                
                if success:
                    updated_count += 1
                    print(f"[SUCCESS] Synced {json_file} to AirTable for user {username}")
                else:
                    print(f"[INFO] Could not update AirTable for {username} - record may not exist")
                    
            except Exception as e:
                print(f"[ERROR] Failed to process {json_file}: {e}")
                continue
        
        return jsonify({
            'success': True,
            'message': f'Sync completed. Updated {updated_count} records.',
            'updated_count': updated_count
        })
        
    except Exception as e:
        print(f"[ERROR] Sync AirTable operation failed: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/admin/users')
def get_admin_users():
    """Get all users who have sent messages for admin dashboard - requires admin authentication"""
    try:
        # Check admin authentication
        admin_key = request.headers.get('Admin-Key') or request.args.get('key')
        if not admin_key:
            return jsonify({'success': False, 'message': 'Admin authentication required'})
        
        lm = get_license_manager()
        auth_result = lm.verify_admin_credentials(admin_key)
        if not auth_result['success']:
            return jsonify({'success': False, 'message': 'Invalid admin credentials'})
        
        # Proceed with admin functionality
        users_data = {}
        
        # Get all messages from Supabase
        response = lm.supabase.table('messages').select('*').execute()
        messages = response.data or []
        
        for message_doc in messages:
            username = message_doc.get('username', '')
            message = message_doc.get('message', '')
            timestamp = message_doc.get('timestamp', '')
            is_admin = message_doc.get('is_admin', False)
            category = message_doc.get('category', 'general')
            status = message_doc.get('status', 'read')
            
            if username:  # Process all messages for this user
                if username not in users_data:
                    users_data[username] = {
                        'username': username,
                        'lastMessage': '',
                        'lastTimestamp': '',
                        'category': 'general',
                        'unreadCount': 0,
                        'totalMessages': 0
                    }
                
                # Only count user messages, not admin replies
                if not is_admin:
                    users_data[username]['totalMessages'] += 1
                    
                    # Only count unread user messages (not admin messages)
                    if status == 'unread':
                        users_data[username]['unreadCount'] += 1
                
                # Keep the most recent message as last message (from either user or admin)
                if timestamp > users_data[username]['lastTimestamp']:
                    users_data[username]['lastMessage'] = message
                    users_data[username]['lastTimestamp'] = timestamp
                    if not is_admin:  # Only update category for user messages
                        users_data[username]['category'] = category
        
        # Convert to list and sort by timestamp
        users_list = list(users_data.values())
        users_list.sort(key=lambda x: x['lastTimestamp'], reverse=True)
        
        return jsonify({
            'success': True,
            'users': users_list,
            'total_users': len(users_list),
            'total_unread': sum(user['unreadCount'] for user in users_list)
        })
        
    except Exception as e:
        print(f"Error getting admin users: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to load users',
            'users': [],
            'total_users': 0,
            'total_unread': 0
        })


if __name__ == "__main__":
    import argparse
    import os
    import threading
    import time
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Fan Finder Server')
    parser.add_argument('--port', type=int, default=5000, help='Port number to run the server on (default: 5000)')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host address to run the server on (default: 0.0.0.0)')
    args = parser.parse_args()

    # Use environment variable as fallback if not provided via argument
    # Check Railway's PORT first, then FLASK_PORT, then command-line arg
    port = int(os.environ.get('PORT', os.environ.get('FLASK_PORT', args.port)))
    
    print(f"[INFO] Web server starting...")
    print("=" * 50)
    print(f"[SERVER READY] Server is running at http://localhost:{port}")
    print("[INFO] Press Ctrl+C to stop the server")
    print("=" * 50)
    
    # Browser opening is handled by the startup scripts
    
    def send_startup_notification():
        """Send startup notification in background"""
        try:
            time.sleep(2)  # Wait for server to be fully ready
            data = {"content": f" Server started running...","username": "FanFindr"}
            webhook_url = get_discord_webhook()
            if webhook_url:
                requests.post(webhook_url, json=data, timeout=2)
        except:
            pass  # Don't break for webhook failures
    
    # Send startup notification in background
    threading.Thread(target=send_startup_notification, daemon=True).start()
    
    try:
        # Start the SocketIO server
        socketio.run(
            app, 
            debug=False, 
            host=args.host, 
            port=port,
            allow_unsafe_werkzeug=True
        )
    except KeyboardInterrupt:
        print(f"\n[STOPPED] Server stopped by user")
        data = {"content": " Server stopped by user","username": "FanFindr"}
        webhook_url = get_discord_webhook()
        if webhook_url:
            try:
                requests.post(webhook_url, json=data, timeout=5)
            except:
                pass 
    except Exception as e:
        print(f"\n[ERROR] Server error: {e}")
        data = {"content": " Server stopped Due to Server Error","username": "FanFindr"}
        webhook_url = get_discord_webhook()
        if webhook_url:
            try:
                requests.post(webhook_url, json=data, timeout=5)
            except:
                pass
    finally:
        print("[INFO] Goodbye!")
        data = {"content": f" Server stopped successfully...Goodbye👋","username": "FanFindr"}
        webhook_url = get_discord_webhook()
        if webhook_url:
            try:
                requests.post(webhook_url, json=data, timeout=5)
            except:
                pass        