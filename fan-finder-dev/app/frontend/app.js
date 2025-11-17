// frontend/app.js - Main application JavaScript

// Utility function to parse timestamps in various formats
function parseTimestamp(timestamp) {
    if (!timestamp) return new Date().toISOString();
    
    try {
        // Handle different timestamp formats
        const date = new Date(timestamp);
        if (date instanceof Date && !isNaN(date)) {
            return date.toISOString();
        } else {
            // Try to parse as string timestamp
            const parsedDate = new Date(timestamp);
            if (parsedDate instanceof Date && !isNaN(parsedDate)) {
                return parsedDate.toISOString();
            }
        }
    } catch (e) {
        console.error('Error parsing timestamp:', timestamp, e);
    }
    
    // Fallback to current time
    return new Date().toISOString();
}

class UserFinderApp {
    constructor() {
            this.socket = null;
            this.isConnected = false;
            this.paymentDetails = '';
            this.scriptStatus = {
                discovery: 'ready',
                keyword: 'ready'
            };
            this.collectedUsers = {
                discovery: [],
                keyword: []
            };
            this.currentlyRunningScript = null; // Track which script is running
            this.checkingStatus = false; // Prevent multiple simultaneous status checks
            this.currentPricing = null; // Store current pricing from Supabase
            this.currentPaymentDetails = null; // Store current payment details from Supabase
            this.userSubscriptionInfo = null; // Store user's subscription tier info
            this.recentTrialActivation = false; // Flag to prevent upgrade modal after trial
            this.currentUser = null; // Store current authenticated user
            
            // Check authentication first
            if (!this.checkAuthentication()) {
                return; // Stop initialization if not authenticated
            }
            
            this.init();
            this.setupPageReloadHandling(); // Add this line
            this.loadCurrentPricing(); // Load pricing from Supabase
            this.loadCurrentPaymentDetails(); // Load payment details from Supabase
            this.loadVersion(); // Load and display version information
            this.initializeTrialButton(); // Initialize trial button visibility
            this.initChat(); // Initialize chat system
        }
        
        setupPageReloadHandling() {
            // Check for running script status when page loads
            this.checkScriptStatusOnLoad();
            
            // Add beforeunload event listener to warn about running scripts
            window.addEventListener('beforeunload', (event) => {
                if (this.currentlyRunningScript) {
                    const message = `A ${this.currentlyRunningScript} script is currently running. If you reload/close the page, you will lose control of the script and it may continue running in the background.`;
                    event.preventDefault();
                    event.returnValue = message;
                    return message;
                }
            });
            
            // Add page visibility change handler to detect when page becomes visible again
            document.addEventListener('visibilitychange', () => {
                if (!document.hidden && this.isConnected) {
                    // Page became visible, check script status
                    setTimeout(() => {
                        this.checkScriptStatusOnLoad();
                        
                        // If a script is running and animation seems stuck, restart it
                        if (this.currentlyRunningScript) {
                            const progressBar = document.getElementById(`${this.currentlyRunningScript}-progress`);
                            if (progressBar && !progressBar.classList.contains('scanning')) {
                                console.log(`🔧 Visibility change: restarting animation for ${this.currentlyRunningScript}`);
                                this.forceAnimationRestart(this.currentlyRunningScript);
                            }
                        }
                    }, 1000);
                }
            });
        }
        
    async checkScriptStatusOnLoad() {
        if (this.checkingStatus) {
            console.log('🔍 Script status check already in progress, skipping...');
            return;
        }
        
        try {
            this.checkingStatus = true;
            console.log('🔍 Checking script status on page load...');
            const response = await fetch('/api/script_status');
            const status = await response.json();
            
            if (status.running && status.script_type) {
                console.log(`📄 Found running script: ${status.script_type}`);
                this.currentlyRunningScript = status.script_type;
                
                // Update UI to show running script
                this.updateScriptStatus(status.script_type, 'running');
                
                // FORCE animation restart
                this.forceAnimationRestart(status.script_type);
                
                // Initialize progress bar for running script
                const targetUsers = parseInt(document.getElementById(`${status.script_type}-target-users`).value) || 300;
                this.updateProgress(status.script_type, {
                    collected_users: this.collectedUsers[status.script_type].length,
                    target_users: targetUsers,
                    progress: 0
                });
                
                // Block the other script
                const otherScript = status.script_type === 'discovery' ? 'keyword' : 'discovery';
                this.updateScriptStatus(otherScript, 'blocked');
                
                // Show notification
                this.showToast(
                    `Found running ${status.script_type.toUpperCase()} script (PID: ${status.pid}). Animation restored.`, 
                    'info', 
                    5000
                );
            } else {
                console.log('✅ No scripts running');
                this.currentlyRunningScript = null;
                
                // Ensure both scripts are ready
                this.updateScriptStatus('discovery', 'ready');
                this.updateScriptStatus('keyword', 'ready');
            }
        } catch (error) {
            console.error('❌ Error checking script status:', error);
        } finally {
            this.checkingStatus = false;
        }
    }
    
    init() {
        console.log('🚀 Initializing User Finder...');
        
        // Initialize Socket.IO connection
        this.initSocket();
        
        // Bind event listeners
        this.bindEvents();
        
        // Initialize UI (connection status will only show if there are issues)
        
        console.log('✅ App initialized');
    }
    
    initSocket() {
            console.log('🔌 Connecting to server...');
            
            // Immediately show connecting status
            this.updateConnectionStatus('connecting');
            
            // Show connecting status after a brief delay if connection takes too long
            const connectingTimeout = setTimeout(() => {
                if (!this.isConnected) {
                    console.log('⚠️ WebSocket connection taking longer than expected...');
                }
            }, 5000);
            
            // Connect to Socket.IO server
            console.log('🔌 Creating Socket.IO connection...');
            this.socket = io({
                timeout: 10000,
                forceNew: true
            });
            
            console.log('🔌 Socket.IO object created:', this.socket);

            this.socket.on('connect', () => {
                console.log('✅ Socket.IO connect event fired!');
                this.isConnected = true;
                clearTimeout(connectingTimeout);
                this.updateConnectionStatus('connected');
                
                // Script status is already checked in setupPageReloadHandling()
                // Extra safety: if we know a script is running, force animation restart
                if (this.currentlyRunningScript) {
                    console.log(`🔧 Emergency animation restore for ${this.currentlyRunningScript}`);
                    this.forceAnimationRestart(this.currentlyRunningScript);
                }
            });

            // Listen for server confirmation
            this.socket.on('connection_confirmed', (data) => {
                console.log('🎉 Server confirmed connection:', data);
                this.isConnected = true;
                clearTimeout(connectingTimeout);
                this.updateConnectionStatus('connected');
            });
            // comment
            this.socket.onAny((eventName, ...args) => {
                if (eventName !== 'script_output') { // Don't spam with output messages
                    console.log(`🔌 [SOCKET EVENT] ${eventName}:`, args);
                }
            });

            // Specific handler for script_progress (if server sends it)
            this.socket.on('script_progress', (data) => {
                console.log(`📊 [SCRIPT_PROGRESS] Received:`, data);
                this.updateProgress(data.script_type, data);
            });

            // Check for any user-related events
            this.socket.on('user_found', (data) => {
                console.log(`👤 [USER_FOUND] Received:`, data);
                if (data.username) {
                    this.addCollectedUser(data.script_type, data.username, data.timestamp || new Date().toLocaleTimeString());
                }
            });
            
            // Handle user collection events from backend
            this.socket.on('user_collected', (data) => {
                console.log(`👤 [USER_COLLECTED] Received:`, data);
                if (data.username && data.script_type) {
                    this.addCollectedUser(data.script_type, data.username, data.timestamp || new Date().toLocaleTimeString());
                }
            });

            // Check for any progress-related events
            this.socket.on('progress_update', (data) => {
                console.log(`📈 [PROGRESS_UPDATE] Received:`, data);
                this.updateProgress(data.script_type, data);
            });

            this.socket.on('reconnect', (attemptNumber) => {
                console.log('🔄 Reconnected to server after', attemptNumber, 'attempts');
                this.isConnected = true;
                this.updateConnectionStatus('connected');
                this.showToast('Reconnected to server!', 'success', 2000);
                
                // Restore script status after reconnection
                setTimeout(() => {
                    this.checkScriptStatusOnLoad();
                }, 500);
            });
            
            this.socket.on('reconnecting', (attemptNumber) => {
                console.log('🔄 Reconnecting... attempt', attemptNumber);
                this.updateConnectionStatus('reconnecting');
            });
            
            this.socket.on('connect_error', (error) => {
                console.error('❌ WebSocket connection error:', error);
                console.error('❌ Error type:', error.type);
                console.error('❌ Error description:', error.description);
                console.error('❌ Error context:', error.context);
                console.error('❌ Error transport:', error.transport);
                clearTimeout(connectingTimeout);
                this.updateConnectionStatus('error');
                
                // Show detailed error message
                this.showToast(`Connection failed: ${error.message || error.description || 'Unknown error'}`, 'danger', 5000);
            });

            // Add more debugging events
            this.socket.on('connect_timeout', () => {
                console.error('❌ Connection timeout');
                this.updateConnectionStatus('error');
                this.showToast('Connection timed out. Please check server.', 'danger', 5000);
            });

            this.socket.on('error', (error) => {
                console.error('❌ Socket error:', error);
                this.showToast(`Socket error: ${error}`, 'danger', 5000);
            });

            this.socket.on('reconnect_error', (error) => {
                console.error('❌ Reconnection error:', error);
            });

            this.socket.on('reconnect_failed', () => {
                console.error('❌ Reconnection failed completely');
                this.updateConnectionStatus('error');
                this.showToast('Failed to reconnect to server', 'danger', 5000);
            });
            
            // Script events
            // Update these socket event handlers in app.js:

            this.socket.on('script_started', (data) => {
                const instanceNumber = data.instance_number || 1;
                console.log(`📄 ${data.script_type} script instance ${instanceNumber} started`);
                this.currentlyRunningScript = data.script_type;

                // Show instance progress bars for ONLY this instance
                if (window.updateInstanceProgress) {
                    window.updateInstanceProgress(data.script_type, 0, 0, 0, instanceNumber);
                }

                // Update ONLY this instance's button state
                if (window.runningInstances) {
                    const key = `${data.script_type}-${instanceNumber}`;
                    window.runningInstances[key] = true;

                    // Update ONLY this button
                    const instanceId = `instance-${data.script_type}-${instanceNumber}`;
                    const btn = document.getElementById(`btn-${instanceId}`);
                    if (btn) {
                        btn.className = 'btn-stop-search';
                        btn.innerHTML = `<i class="fas fa-stop me-2"></i>Stop ${data.script_type === 'discovery' ? 'Discovery Search' : 'Keyword Search'}`;
                    }
                }

                this.showToast(`${data.script_type.toUpperCase()} instance ${instanceNumber} started and scanning!`, 'success');

                // Update instance counts
                if (window.updateInstanceCounts) {
                    window.updateInstanceCounts();
                }
            });

            // Script output - Run silently in background without showing credentials
            this.socket.on('script_output', (data) => {
                // Log only progress updates (don't display credentials)
                if (data.output.includes('SUCCESS') || data.output.includes('%')) {
                    console.log(`📊 [PROGRESS] ${data.script_type}: "${data.output}"`);
                } else {
                    // Silent logging - don't process other output to avoid showing credentials
                    console.log(`🔇 [BACKGROUND] ${data.script_type}: Running silently...`);
                }

                // Only process progress updates, skip other messages to avoid credentials
                if (data.output.includes('Collected user') || data.output.includes('New user found')) {
                    this.checkForNewUser(data.script_type, data.output, data.timestamp);
                }

                // Ensure animation continues
                if (this.currentlyRunningScript === data.script_type) {
                    const progressBar = document.getElementById(`${data.script_type}-progress`);
                    if (progressBar && !progressBar.classList.contains('scanning')) {
                        progressBar.classList.add('progress-bar-animated', 'progress-bar-striped', 'scanning');
                    }
                }
            });
            
            this.socket.on('script_finished', (data) => {
                console.log(`🏁 ${data.script_type} script finished:`, data);
                this.currentlyRunningScript = null;
                this.updateScriptStatus(data.script_type, 'ready');
                
                const message = data.success 
                    ? `${data.script_type.toUpperCase()} completed! Collected ${data.collected_users} users.`
                    : `${data.script_type.toUpperCase()} failed. Check logs for details.`;
                    
                this.showToast(message, data.success ? 'success' : 'danger');
            });
            
            this.socket.on('script_stopped', (data) => {
                const instanceNumber = data.instance_number || 1;
                console.log(`⏹️ ${data.script_type} script instance ${instanceNumber} stopped`);
                this.currentlyRunningScript = null;
                this.updateScriptStatus(data.script_type, 'ready');
                this.showToast(`${data.script_type.toUpperCase()} instance ${instanceNumber} stopped.`, 'warning');

                // Hide instance progress bar for ONLY this instance
                if (window.hideInstanceProgress) {
                    window.hideInstanceProgress(data.script_type, instanceNumber);
                }

                // Update ONLY this instance's button state - mark as stopped
                if (window.runningInstances) {
                    const key = `${data.script_type}-${instanceNumber}`;
                    window.runningInstances[key] = false;

                    // Update ONLY this button
                    const instanceId = `instance-${data.script_type}-${instanceNumber}`;
                    const btn = document.getElementById(`btn-${instanceId}`);
                    if (btn) {
                        btn.className = 'btn-start-search';
                        btn.innerHTML = `<i class="fas fa-play me-2"></i>Start ${data.script_type === 'discovery' ? 'Discovery Search' : 'Keyword Search'}`;
                    }
                }

                // Update instance counts
                if (window.updateInstanceCounts) {
                    window.updateInstanceCounts();
                }
            });

            this.socket.on('script_error', (data) => {
                const instanceNumber = data.instance_number || 1;
                console.error(`❌ ${data.script_type} script instance ${instanceNumber} error:`, data.error);
                this.currentlyRunningScript = null;
                this.updateScriptStatus(data.script_type, 'ready');
                this.showToast(`Error in instance ${instanceNumber}: ${data.error}`, 'danger');

                // Hide instance progress bar for ONLY this instance
                if (window.hideInstanceProgress) {
                    window.hideInstanceProgress(data.script_type, instanceNumber);
                }

                // Update ONLY this instance's button state - mark as stopped on error
                if (window.runningInstances) {
                    const key = `${data.script_type}-${instanceNumber}`;
                    window.runningInstances[key] = false;

                    // Update ONLY this button
                    const instanceId = `instance-${data.script_type}-${instanceNumber}`;
                    const btn = document.getElementById(`btn-${instanceId}`);
                    if (btn) {
                        btn.className = 'btn-start-search';
                        btn.innerHTML = `<i class="fas fa-play me-2"></i>Start ${data.script_type === 'discovery' ? 'Discovery Search' : 'Keyword Search'}`;
                    }
                }

                // Update instance counts
                if (window.updateInstanceCounts) {
                    window.updateInstanceCounts();
                }
            });
            

            this.socket.on('script_status_update', (data) => {
                console.log(`📊 Script status update:`, data);
                if (data.running && data.script_type) {
                    this.currentlyRunningScript = data.script_type;
                    
                    // Set status to running
                    this.updateScriptStatus(data.script_type, 'running');
                    
                    // FORCE animation restart after reconnection
                    this.forceAnimationRestart(data.script_type);
                    
                    // Update progress text
                    const progressText = document.querySelector(`#${data.script_type}-progress span`);
                    if (progressText) {
                        const target = parseInt(document.getElementById(`${data.script_type}-target-users`).value) || 0;
                        progressText.textContent = `Scanning... (${this.collectedUsers[data.script_type].length}/${target} users)`;
                    }
                    
                    // Update the info text
                    const info = document.getElementById(`${data.script_type}-info`);
                    if (info) {
                        info.textContent = '🔄 Script reconnected and scanning...';
                        info.className = 'text-primary';
                    }
                    
                    // Block the other script
                    const otherScript = data.script_type === 'discovery' ? 'keyword' : 'discovery';
                    this.updateScriptStatus(otherScript, 'blocked');
                    
                    // Show reconnection toast
                    this.showToast(`Reconnected to running ${data.script_type.toUpperCase()} script`, 'info', 3000);
                    
                } else {
                    this.currentlyRunningScript = null;
                    this.updateScriptStatus('discovery', 'ready');
                    this.updateScriptStatus('keyword', 'ready');
                }
            });
        }
    
    bindEvents() {
            // Discovery Search Events (with null checks for new instance-based UI)
            const discoveryStartBtn = document.getElementById('discovery-start-btn');
            if (discoveryStartBtn) {
                discoveryStartBtn.addEventListener('click', () => {
                    this.startScript('discovery');
                });
            }

            const discoveryStopBtn = document.getElementById('discovery-stop-btn');
            if (discoveryStopBtn) {
                discoveryStopBtn.addEventListener('click', () => {
                    this.stopScript('discovery');
                });
            }

            // Keyword Search Events (with null checks for new instance-based UI)
            const keywordStartBtn = document.getElementById('keyword-start-btn');
            if (keywordStartBtn) {
                keywordStartBtn.addEventListener('click', () => {
                    this.startScript('keyword');
                });
            }

            const keywordStopBtn = document.getElementById('keyword-stop-btn');
            if (keywordStopBtn) {
                keywordStopBtn.addEventListener('click', () => {
                    this.stopScript('keyword');
                });
            }

            // Initialize model selection dropdowns (with null checks)
            try {
                this.initializeModelDropdown('discovery');
            } catch (e) {
                console.log('Discovery dropdown already initialized by instance system');
            }
            try {
                this.initializeModelDropdown('keyword');
            } catch (e) {
                console.log('Keyword dropdown already initialized by instance system');
            }

            // Form submission prevention (with null checks for new instance-based UI)
            const discoveryForm = document.getElementById('discovery-form');
            if (discoveryForm) {
                discoveryForm.addEventListener('submit', (e) => {
                    e.preventDefault();
                    this.startScript('discovery');
                });
            }

            const keywordForm = document.getElementById('keyword-form');
            if (keywordForm) {
                keywordForm.addEventListener('submit', (e) => {
                    e.preventDefault();
                    this.startScript('keyword');
                });
            }
            
            
            
            // Initialize progress bars to show 0/target format on page load
            this.initializeProgressBars();
        }
        
        initializeProgressBars() {
            ['discovery', 'keyword'].forEach(scriptType => {
                const targetInput = document.getElementById(`${scriptType}-target-users`);
                const progressBar = document.getElementById(`${scriptType}-progress`);

                // Skip if old UI elements don't exist (using new instance-based UI)
                if (!progressBar) {
                    console.log(`ℹ️ Old progress bar for ${scriptType} not found (using new instance-based UI)`);
                    return;
                }

                const progressText = progressBar.querySelector('span');

                if (targetInput && progressText) {
                    const updateProgressDisplay = () => {
                        const target = parseInt(targetInput.value) || 0;
                        progressText.textContent = `0/${target} users (0%)`;
                    };
                    
                    // Validate Target Fans limits based on subscription tier
                    const validateTargetFans = () => {
                        console.log(`🔍 [INPUT_VALIDATION] ${scriptType} - Checking limits...`);
                        console.log(`🔍 [INPUT_VALIDATION] userSubscriptionInfo:`, this.userSubscriptionInfo);
                        
                        if (this.userSubscriptionInfo) {
                            const inputValue = targetInput.value.trim();
                            
                            // Don't validate if field is empty or being cleared
                            if (inputValue === '' || inputValue === '0') {
                                console.log(`⚪ [INPUT_VALIDATION] Field is empty or zero, skipping validation`);
                                return;
                            }
                            
                            const requestedFans = parseInt(inputValue);
                            const maxFans = this.userSubscriptionInfo.max_fans;
                            
                            // Don't validate if the parsed number is invalid
                            if (isNaN(requestedFans) || requestedFans <= 0) {
                                console.log(`⚪ [INPUT_VALIDATION] Invalid number, skipping validation`);
                                return;
                            }
                            
                            console.log(`🎯 [INPUT_VALIDATION] ${scriptType} - Requested: ${requestedFans}, Max: ${maxFans}, Tier: ${this.userSubscriptionInfo.tier}`);
                            
                            // Only show modal if user tries to exceed the limit
                            if (maxFans > 0 && requestedFans > maxFans) {
                                console.log(`❌ [INPUT_VALIDATION] Limit exceeded! Correcting ${requestedFans} to ${maxFans}`);
                                // Correct the value first
                                targetInput.value = maxFans;
                                updateProgressDisplay();
                                // Show upgrade modal
                                this.showUpgradeModal(this.userSubscriptionInfo.tier, maxFans, requestedFans);
                            } else {
                                console.log(`✅ [INPUT_VALIDATION] Limit check passed - ${requestedFans} is within limit of ${maxFans}`);
                            }
                        } else {
                            console.log(`⚠️ [INPUT_VALIDATION] No subscription info available yet`);
                        }
                    };
                    
                    // Initial display
                    updateProgressDisplay();
                    
                    // Update when target changes
                    targetInput.addEventListener('input', () => {
                        updateProgressDisplay();
                        validateTargetFans();
                    });
                    
                    // Validate on blur (when user leaves the field)
                    targetInput.addEventListener('blur', validateTargetFans);
                }
            });
        }

        // ========== MODEL DROPDOWN FUNCTIONS ==========
        initializeModelDropdown(scriptType) {
            const searchInput = document.getElementById(`${scriptType}-model-search`);
            const dropdown = document.getElementById(`${scriptType}-model-dropdown`);
            const modelIdInput = document.getElementById(`${scriptType}-model-id`);

            if (!searchInput || !dropdown) return;

            // Preload all models in background (don't display yet)
            this.loadModelsForDropdown(scriptType);

            // Show all models when user clicks/focuses on the search field
            searchInput.addEventListener('focus', () => {
                // Show dropdown with all models (don't display if empty)
                if (dropdown.innerHTML.trim() !== '') {
                    dropdown.style.display = 'block';
                }
            });

            // Handle search input - filter models as user types
            searchInput.addEventListener('input', (e) => {
                const query = e.target.value.trim();
                if (query.length > 0) {
                    // User is searching - filter models
                    this.searchModelsForDropdown(scriptType, query);
                    dropdown.style.display = 'block';
                } else {
                    // User cleared the input - show all models
                    this.loadModelsForDropdown(scriptType, true);
                    dropdown.style.display = 'block';
                }
            });

            // Hide dropdown when clicking outside
            document.addEventListener('click', (e) => {
                if (!searchInput.contains(e.target) && !dropdown.contains(e.target)) {
                    dropdown.style.display = 'none';
                }
            });
        }

        async loadModelsForDropdown(scriptType, show = false) {
            try {
                const response = await fetch('/api/models');
                const data = await response.json();

                if (data.success) {
                    // Load models and optionally display them
                    this.renderModelDropdown(scriptType, data.models, show);
                }
            } catch (error) {
                console.error('Error loading models:', error);
            }
        }

        async searchModelsForDropdown(scriptType, query) {
            try {
                const response = await fetch(`/api/models/search?q=${encodeURIComponent(query)}`);
                const data = await response.json();

                if (data.success) {
                    this.renderModelDropdown(scriptType, data.models);
                }
            } catch (error) {
                console.error('Error searching models:', error);
            }
        }

        renderModelDropdown(scriptType, models, show = true) {
            const dropdown = document.getElementById(`${scriptType}-model-dropdown`);
            const searchInput = document.getElementById(`${scriptType}-model-search`);

            if (!models || models.length === 0) {
                dropdown.innerHTML = '<div style="padding: 10px; color: #999;">No models found</div>';
                if (show) dropdown.style.display = 'block';
                return;
            }

            let html = '';
            models.forEach(model => {
                html += `
                    <div style="padding: 10px 15px; cursor: pointer; border-bottom: 1px solid #eee; transition: background-color 0.2s;"
                         onmouseover="this.style.backgroundColor='#f5f5f5'"
                         onmouseout="this.style.backgroundColor='white'"
                         onclick="app.selectModel('${scriptType}', '${model.id}', '${model.model_name}')">
                        <div style="font-weight: 500; color: #333;">${model.model_name}</div>
                        ${model.description ? `<div style="font-size: 12px; color: #666; margin-top: 3px;">${model.description}</div>` : ''}
                    </div>
                `;
            });
            dropdown.innerHTML = html;
            if (show) dropdown.style.display = 'block';
        }

        selectModel(scriptType, modelId, modelName) {
            document.getElementById(`${scriptType}-model-search`).value = modelName;
            document.getElementById(`${scriptType}-model-id`).value = modelId;
            document.getElementById(`${scriptType}-model-dropdown`).style.display = 'none';
            console.log(`✅ Selected model "${modelName}" for ${scriptType}`);
        }

    async startScript(scriptType) {
        if (!this.isConnected) {
            this.showToast('Not connected to server. Please refresh the page.', 'danger');
            return;
        }
        
        // Get form data
        const settings = this.getScriptSettings(scriptType);
        
        // Validate form
        if (!this.validateSettings(settings, scriptType)) {
            return;
        }
        
        console.log(`🚀 Starting ${scriptType} script...`);

        // Model-based accounts skip all subscription checks
        console.log(`✅ Using model account - skipping subscription validation`);

        // IMMEDIATELY update UI to starting state with animation
        this.updateScriptStatus(scriptType, 'starting');

        // Send start command to server
        this.socket.emit('start_script', {
            script_type: scriptType,
            settings: settings
        });
    }
    
    stopScript(scriptType) {
        if (!this.isConnected) {
            this.showToast('Not connected to server.', 'danger');
            return;
        }
        
        console.log(`⏹️ Stopping ${scriptType} script...`);
        
        // Update UI to stopping state immediately
        this.updateScriptStatus(scriptType, 'stopping');
        
        this.socket.emit('stop_script', {
            script_type: scriptType
        });
        
        // Set a timeout to reset the UI in case the server doesn't respond
        setTimeout(() => {
            if (this.scriptStatus[scriptType] === 'stopping') {
                console.log(`⚠️ Stop timeout for ${scriptType}, forcing UI reset`);
                this.updateScriptStatus(scriptType, 'ready');
                this.showToast(`${scriptType.toUpperCase()} script stop timeout - UI reset`, 'warning');
            }
        }, 15000); // 15 second timeout for browser cleanup
    }
    
    getScriptSettings(scriptType) {
        const prefix = scriptType;

        const settings = {
            model_id: document.getElementById(`${prefix}-model-id`).value,
            target_users: parseInt(document.getElementById(`${prefix}-target-users`).value),
            headless: true  // Always run in background (Realtime Preview toggle removed)
        };

        // Add script-specific settings
        if (scriptType === 'discovery') {
            settings.posts_per_filter = parseInt(document.getElementById('discovery-posts-per-filter').value);
        } else if (scriptType === 'keyword') {
            settings.posts_per_keyword = parseInt(document.getElementById('keyword-posts-per-keyword').value);
        }

        return settings;
    }

    validateSettings(settings, scriptType) {
        if (!settings.model_id) {
            this.showToast('Please select a model.', 'warning');
            return false;
        }

        if (!settings.target_users || settings.target_users <= 0) {
            this.showToast('Please enter a valid target users number.', 'warning');
            return false;
        }

        return true;
    }

    forceAnimationRestart(scriptType) {
        const progressBar = document.getElementById(`${scriptType}-progress`);
        if (!progressBar) return;
        
        console.log(`🔧 Force restarting animation for ${scriptType}`);
        
        // Step 1: Stop animation
        progressBar.classList.add('force-restart');
        progressBar.classList.remove('scanning', 'progress-bar-animated', 'progress-bar-striped');
        
        // Step 2: Force reflow
        progressBar.offsetHeight;
        
        // Step 3: Restart animation after a brief delay
        setTimeout(() => {
            progressBar.classList.remove('force-restart');
            progressBar.classList.add('progress-bar-animated', 'progress-bar-striped', 'scanning');
            progressBar.style.width = '100%';
            progressBar.setAttribute('data-scanning', 'true');
            
            // Force another reflow
            progressBar.offsetHeight;
            
            console.log(`✅ Animation restarted for ${scriptType}`);
        }, 50);
    }

    async checkSubscription(username, scriptType) {
        // Store username and scriptType for use in subscription modal
        this.lastCheckedUsername = username;
        this.lastCheckedScriptType = scriptType;
        
        try {
            console.log(`🔍 Checking subscription for: ${username}`);
            
            const response = await fetch('/api/check_subscription', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ username: username })
            });
            
            const data = await response.json();
            
            if (data.success) {
                // Store subscription info
                this.userSubscriptionInfo = data.subscription_info;
                console.log('🔍 [SUBSCRIPTION] Stored subscription info:', this.userSubscriptionInfo);
                
                // Check if user is eligible for free trial
                this.checkTrialEligibility();
                
                // Validate Target Fans limit
                const targetFansInput = document.getElementById(`${scriptType}-target-users`);
                if (targetFansInput && this.userSubscriptionInfo) {
                    const inputValue = targetFansInput.value.trim();
                    const requestedFans = parseInt(inputValue) || 100;
                    const maxFans = this.userSubscriptionInfo.max_fans;
                    
                    console.log(`🎯 [VALIDATION] ${scriptType} - Requested: ${requestedFans}, Max allowed: ${maxFans}, Tier: ${this.userSubscriptionInfo.tier}`);
                    
                    // Only validate if it's a valid number and exceeds limit
                    if (maxFans > 0 && requestedFans > maxFans && inputValue !== '' && !isNaN(requestedFans) && requestedFans > 0) {
                        console.log(`❌ [VALIDATION] Limit exceeded! ${requestedFans} > ${maxFans}`);
                        targetFansInput.value = maxFans;
                        targetFansInput.focus();
                        // Show upgrade modal instead of toast
                        this.showUpgradeModal(this.userSubscriptionInfo.tier, maxFans, requestedFans);
                        return false;
                    } else {
                        console.log(`✅ [VALIDATION] Limit check passed: ${requestedFans} <= ${maxFans}`);
                    }
                    
                    // Update input max attribute and placeholder
                    if (maxFans > 0) {
                        targetFansInput.max = maxFans;
                        targetFansInput.placeholder = `Max ${maxFans} fans (${this.userSubscriptionInfo.tier} plan)`;
                        console.log(`🔧 [UI] Updated input max=${maxFans}, placeholder updated`);
                    } else {
                        targetFansInput.removeAttribute('max');
                        targetFansInput.placeholder = `Unlimited fans (${this.userSubscriptionInfo.tier} plan)`;
                        console.log(`🔧 [UI] Set unlimited mode for ${this.userSubscriptionInfo.tier} plan`);
                    }
                }
                
                this.showToast(data.message, 'success');
                return true;
            } else {
                console.log('❌ Subscription check failed:', data);
                // Instead of showing subscription modal, switch to pricing tab to show all plans
                this.switchToPricingTab();
                return false;
            }
            
        } catch (error) {
            console.error('❌ Subscription check error:', error);
            this.showToast(`Connection error: ${error.message}`, 'danger');
            return false;
        }
    }
    
    async loadCurrentPricing() {
        try {
            const response = await fetch('/api/get_pricing');
            const data = await response.json();
            
            if (data.success) {
                this.currentPricing = data.pricing;
                console.log('[PRICING] Loaded current pricing from Supabase:', this.currentPricing);
                this.updatePricingDisplay(); // Update the pricing display
            } else {
                console.warn('[PRICING] Failed to load pricing:', data.message);
                // Fallback pricing
                this.currentPricing = {
                    monthly_price: 19.99,
                    currency: 'EUR',
                    source: 'fallback'
                };
                this.updatePricingDisplay(); // Update with fallback pricing
            }
        } catch (error) {
            console.error('[PRICING] Error loading pricing:', error);
            // Fallback pricing
            this.currentPricing = {
                monthly_price: 19.99,
                currency: 'EUR',
                source: 'fallback'
            };
            this.updatePricingDisplay(); // Update with fallback pricing
        }
    }

    updatePricingDisplay() {
        if (!this.currentPricing) return;
        
        const monthlyPrice = this.currentPricing.monthly_price;
        const currency = this.currentPricing.currency === 'EUR' ? '€' : this.currentPricing.currency;
        
        // Calculate discounted prices and savings
        const sixMonthOriginal = monthlyPrice * 6;
        const sixMonthDiscounted = Math.round(sixMonthOriginal * 0.7); // 30% off
        const sixMonthSavings = sixMonthOriginal - sixMonthDiscounted;
        
        const yearlyOriginal = monthlyPrice * 12;
        const yearlyDiscounted = Math.round(yearlyOriginal * 0.5); // 50% off
        const yearlySavings = yearlyOriginal - yearlyDiscounted;
        
        // Update 1 Month pricing
        const monthlyPriceCurrency = document.getElementById('monthly-price-currency');
        const monthlyPriceElement = document.getElementById('monthly-price');
        if (monthlyPriceCurrency && monthlyPriceElement) {
            monthlyPriceCurrency.textContent = currency;
            monthlyPriceElement.textContent = monthlyPrice;
        }
        
        // Update 6 Months pricing
        const sixMonthOriginalCurrency = document.getElementById('sixmonth-original-currency');
        const sixMonthOriginalPrice = document.getElementById('sixmonth-original-price');
        const sixMonthPriceCurrency = document.getElementById('sixmonth-price-currency');
        const sixMonthPriceElement = document.getElementById('sixmonth-price');
        
        if (sixMonthOriginalCurrency && sixMonthOriginalPrice && sixMonthPriceCurrency && sixMonthPriceElement) {
            sixMonthOriginalCurrency.textContent = currency;
            sixMonthOriginalPrice.textContent = sixMonthOriginal;
            sixMonthPriceCurrency.textContent = currency;
            sixMonthPriceElement.textContent = sixMonthDiscounted;
        }
        
        // Update 1 Year pricing
        const yearlyOriginalCurrency = document.getElementById('yearly-original-currency');
        const yearlyOriginalPrice = document.getElementById('yearly-original-price');
        const yearlyPriceCurrency = document.getElementById('yearly-price-currency');
        const yearlyPriceElement = document.getElementById('yearly-price');
        
        if (yearlyOriginalCurrency && yearlyOriginalPrice && yearlyPriceCurrency && yearlyPriceElement) {
            yearlyOriginalCurrency.textContent = currency;
            yearlyOriginalPrice.textContent = yearlyOriginal;
            yearlyPriceCurrency.textContent = currency;
            yearlyPriceElement.textContent = yearlyDiscounted;
        }
        
        // Update savings display
        const sixMonthSavingsCurrency = document.getElementById('sixmonth-savings-currency');
        const sixMonthSavingsElement = document.getElementById('sixmonth-savings');
        
        if (sixMonthSavingsCurrency && sixMonthSavingsElement) {
            sixMonthSavingsCurrency.textContent = currency;
            sixMonthSavingsElement.textContent = sixMonthSavings;
        }
        
        const yearlySavingsCurrency = document.getElementById('yearly-savings-currency');
        const yearlySavingsElement = document.getElementById('yearly-savings');
        
        if (yearlySavingsCurrency && yearlySavingsElement) {
            yearlySavingsCurrency.textContent = currency;
            yearlySavingsElement.textContent = yearlySavings;
        }
        
        console.log('[PRICING] Display updated - Monthly:', monthlyPrice, currency);
        console.log('[PRICING] 6 Months:', sixMonthOriginal, '->', sixMonthDiscounted, '(Save', sixMonthSavings, currency + ')');
        console.log('[PRICING] 1 Year:', yearlyOriginal, '->', yearlyDiscounted, '(Save', yearlySavings, currency + ')');
    }

    async loadCurrentPaymentDetails() {
        try {
            const response = await fetch('/api/get_payment_details');
            const data = await response.json();
            
            if (data.success) {
                this.currentPaymentDetails = data.payment_details;
                console.log('[PAYMENT] Loaded current payment details from Supabase:', this.currentPaymentDetails);
            } else {
                console.warn('[PAYMENT] Failed to load payment details:', data.message);
                // Fallback payment details
                this.currentPaymentDetails = {
                    iban: 'LU524080000056226794',
                    bic: 'BCIRLULL',
                    beneficiary: 'Noel Periarce',
                    source: 'fallback'
                };
            }
        } catch (error) {
            console.error('[PAYMENT] Error loading payment details:', error);
            // Fallback payment details
            this.currentPaymentDetails = {
                iban: 'LU524080000056226794',
                bic: 'BCIRLULL',
                beneficiary: 'Noel Periarce',
                source: 'fallback'
            };
        }
    }

    async loadVersion() {
        try {
            const response = await fetch('/version.json');
            const versionData = await response.json();
            
            if (versionData.version) {
                console.log('[VERSION] Loaded version:', versionData);
                this.displayVersion(versionData);
            } else {
                console.warn('[VERSION] Invalid version data received');
                this.displayVersion({ version: '1.0.0', description: 'Unknown version' });
            }
        } catch (error) {
            console.error('[VERSION] Error loading version:', error);
            // Fallback version
            this.displayVersion({ version: '1.0.0', description: 'Version unavailable' });
        }
    }

    displayVersion(versionData) {
        const version = versionData.version || '1.0.0';
        
        // Update all version display elements
        const loadingVersion = document.getElementById('loading-version');
        const navbarVersion = document.getElementById('navbar-version');
        const instructionsVersion = document.getElementById('instructions-version');
        
        if (loadingVersion) {
            loadingVersion.textContent = `v${version}`;
        }
        
        if (navbarVersion) {
            navbarVersion.textContent = `v${version}`;
        }
        
        if (instructionsVersion) {
            instructionsVersion.textContent = `v${version}`;
        }
        
        // Update page title to include version
        document.title = `Fan Finder v${version} - Web Interface`;
        
        console.log(`[VERSION] Displayed version ${version} in UI`);
    }

    showUpgradeModal(currentTier, maxFans, requestedFans) {
        // Don't show upgrade modal immediately after trial activation
        if (this.recentTrialActivation) {
            console.log('🎁 [UPGRADE_MODAL] Skipping upgrade modal - recent trial activation');
            return;
        }
        
        // Create upgrade modal
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.setAttribute('tabindex', '-1');
        
        // Get tier recommendations
        let recommendedPlans = [];
        if (requestedFans <= 100) {
            recommendedPlans.push({
                name: '6 Months Plan',
                tier: 'pro',
                limit: '100 fans',
                badge: 'Popular',
                price: this.calculatePlanPrice('6month'),
                savings: this.calculatePlanSavings('6month'),
                button: 'btn-dark'
            });
        }
        
        recommendedPlans.push({
            name: '1 Year Plan', 
            tier: 'premium',
            limit: 'Unlimited fans',
            badge: 'Best Value',
            price: this.calculatePlanPrice('1year'),
            savings: this.calculatePlanSavings('1year'),
            button: 'btn-success'
        });

        modal.innerHTML = `
            <div class="modal-dialog modal-dialog-centered modal-lg">
                <div class="modal-content border-0 shadow-lg">
                    <!-- Header -->
                    <div class="modal-header border-0 text-center" style="background: linear-gradient(135deg, #ff6b35 0%, #f7931e 100%); color: white;">
                        <div class="w-100 text-center">
                            <div class="mb-2">
                                <i class="fas fa-crown fa-2x"></i>
                            </div>
                            <h4 class="mb-1 fw-bold">Upgrade Required</h4>
                            <small class="opacity-90">Unlock more Target Fans</small>
                        </div>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    
                    <!-- Body -->
                    <div class="modal-body p-4">
                        <div class="text-center mb-4">
                            <div class="alert alert-warning border-0" style="background: rgba(255, 107, 53, 0.1);">
                                <div class="d-flex align-items-center justify-content-center">
                                    <i class="fas fa-exclamation-triangle text-warning me-3 fa-2x"></i>
                                    <div>
                                        <h6 class="mb-1 fw-bold">Target Fans Limit Reached</h6>
                                        <small>You requested <strong>${requestedFans} fans</strong>, but your <strong>${currentTier} plan</strong> allows maximum <strong>${maxFans} fans</strong></small>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <h6 class="text-center mb-4 fw-bold">🚀 Upgrade to get more Target Fans:</h6>
                        
                        <div class="row">
                            ${recommendedPlans.map(plan => `
                                <div class="col-md-6 mb-3">
                                    <div class="card h-100 border-2" style="border-color: ${plan.button === 'btn-dark' ? '#333' : '#28a745'} !important;">
                                        <div class="card-header text-center ${plan.button === 'btn-dark' ? 'bg-dark' : 'bg-success'} text-white">
                                            <small class="badge bg-light ${plan.button === 'btn-dark' ? 'text-dark' : 'text-success'}">${plan.badge}</small>
                                        </div>
                                        <div class="card-body text-center p-3">
                                            <h5 class="fw-bold">${plan.name}</h5>
                                            <div class="mb-2">
                                                <div class="h4 ${plan.button === 'btn-dark' ? 'text-dark' : 'text-success'} mb-0">
                                                    ${plan.price}
                                                </div>
                                                <small class="text-muted">total</small>
                                            </div>
                                            <div class="mb-3">
                                                <div class="badge ${plan.button === 'btn-dark' ? 'bg-success' : 'bg-danger'} mb-2">${plan.savings}</div>
                                                <div class="fw-bold text-primary">📈 ${plan.limit}</div>
                                            </div>
                                            <button class="btn ${plan.button} w-100 fw-bold" onclick="window.app.switchToPricingTab(); bootstrap.Modal.getInstance(this.closest('.modal')).hide();">
                                                Choose Plan
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                        
                        <div class="text-center mt-4">
                            <p class="text-muted mb-2">
                                <i class="fas fa-info-circle me-1"></i>
                                Your Target Fans has been automatically adjusted to <strong>${maxFans}</strong> for now
                            </p>
                        </div>
                    </div>
                    
                    <!-- Footer -->
                    <div class="modal-footer border-0 bg-light">
                        <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">
                            <i class="fas fa-check me-2"></i>Continue with ${maxFans} fans
                        </button>
                        <button type="button" class="btn btn-primary fw-bold" onclick="window.app.switchToPricingTab(); bootstrap.Modal.getInstance(this.closest('.modal')).hide();">
                            <i class="fas fa-crown me-2"></i>View Pricing Plans
                        </button>
                        <button type="button" class="btn btn-outline-danger" data-bs-dismiss="modal">
                            <i class="fas fa-times me-2"></i>Close
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        const modalInstance = new bootstrap.Modal(modal);
        modalInstance.show();
        
        // Clean up modal after closing
        modal.addEventListener('hidden.bs.modal', () => {
            document.body.removeChild(modal);
        });
    }
    
    calculatePlanPrice(plan) {
        if (!this.currentPricing) return '€20';
        
        const monthly = this.currentPricing.monthly_price;
        const currency = this.currentPricing.currency === 'EUR' ? '€' : this.currentPricing.currency;
        
        switch(plan) {
            case '6month':
                return `${currency}${Math.round(monthly * 6 * 0.7)}`;
            case '1year':
                return `${currency}${Math.round(monthly * 12 * 0.5)}`;
            default:
                return `${currency}${monthly}`;
        }
    }
    
    calculatePlanSavings(plan) {
        if (!this.currentPricing) return 'Save €36';
        
        const monthly = this.currentPricing.monthly_price;
        const currency = this.currentPricing.currency === 'EUR' ? '€' : this.currentPricing.currency;
        
        switch(plan) {
            case '6month':
                const sixMonthSavings = (monthly * 6) - Math.round(monthly * 6 * 0.7);
                return `Save ${currency}${sixMonthSavings}`;
            case '1year':
                const yearlySavings = (monthly * 12) - Math.round(monthly * 12 * 0.5);
                return `Save ${currency}${yearlySavings}`;
            default:
                return '';
        }
    }
    
    switchToPricingTab() {
        // Switch to pricing tab
        const pricingTab = document.getElementById('pricing-tab');
        if (pricingTab) {
            pricingTab.click();
            
            // Show a toast message to guide the user
            setTimeout(() => {
                this.showToast('Please select a subscription plan to continue', 'info');
            }, 500);
        }
    }
    
    initializeTrialButton() {
        // Show trial button by default when app loads (for new users)
        const trialBtn = document.getElementById('trial-btn');
        const trialInfo = document.getElementById('trial-info');
        
        if (trialBtn && trialInfo) {
            trialBtn.style.display = 'block';
            trialInfo.style.display = 'block';
            console.log(`🎁 [TRIAL] Initialized - showing trial button by default`);
        }
    }
    
    checkTrialEligibility() {
        const trialBtn = document.getElementById('trial-btn');
        const trialInfo = document.getElementById('trial-info');
        
        if (!trialBtn || !trialInfo) return;
        
        // Show trial button only for users who haven't used trial yet and don't have active subscription
        if (this.userSubscriptionInfo) {
            const hasActiveSub = this.userSubscriptionInfo.status === 'active';
            const trialUsed = this.userSubscriptionInfo.trial_used || false;
            const tier = this.userSubscriptionInfo.tier || 'basic';
            
            console.log(`🎁 [TRIAL] Checking eligibility - Active: ${hasActiveSub}, Trial used: ${trialUsed}, Tier: ${tier}`);
            
            if (hasActiveSub && tier !== 'basic') {
                // User has premium/enterprise subscription, hide trial
                trialBtn.style.display = 'none';
                trialInfo.style.display = 'none';
                console.log(`🎁 [TRIAL] Hidden - user has ${tier} subscription`);
            } else if (trialUsed) {
                // User has already used trial, hide button
                trialBtn.style.display = 'none';
                trialInfo.style.display = 'none';
                console.log(`🎁 [TRIAL] Hidden - trial already used`);
            } else {
                // User is eligible for trial
                trialBtn.style.display = 'block';
                trialInfo.style.display = 'block';
                console.log(`🎁 [TRIAL] Shown - user eligible for free trial`);
            }
        } else {
            // No subscription info yet, show trial for new users
            trialBtn.style.display = 'block';
            trialInfo.style.display = 'block';
            console.log(`🎁 [TRIAL] Shown - new user, no subscription info`);
        }
    }
    
    async activateFreeTrial(selectedUsername = null) {
        console.log('🎁 [TRIAL] Activating free trial...', 'Username:', selectedUsername);
        
        // Get username from parameter or form
        let username = selectedUsername || '';
        
        if (!username) {
            // Fallback to form fields for backwards compatibility
            const discoveryEmail = document.getElementById('discovery-email');
            const keywordEmail = document.getElementById('keyword-email');
            
            console.log('🎁 [TRIAL] Checking for username in forms...');
            console.log('🎁 [TRIAL] Discovery email:', discoveryEmail ? discoveryEmail.value : 'not found');
            console.log('🎁 [TRIAL] Keyword email:', keywordEmail ? keywordEmail.value : 'not found');
            
            if (discoveryEmail && discoveryEmail.value.trim()) {
                username = discoveryEmail.value.trim();
                console.log('🎁 [TRIAL] Using username from discovery form:', username);
            } else if (keywordEmail && keywordEmail.value.trim()) {
                username = keywordEmail.value.trim();
                console.log('🎁 [TRIAL] Using username from keyword form:', username);
            } else {
                // Prompt user for username
                username = prompt('Enter your username to activate free trial:');
                console.log('🎁 [TRIAL] Username from prompt:', username);
                if (!username || username.trim() === '') {
                    console.log('🎁 [TRIAL] No username provided, aborting');
                    this.showToast('Username required for trial activation', 'warning');
                    return;
                }
                username = username.trim();
            }
        }
        
        // Show loading state
        const trialBtn = document.getElementById('trial-btn');
        if (trialBtn) {
            trialBtn.disabled = true;
            trialBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Activating...';
        }
        
        try {
            console.log('🎁 [TRIAL] Sending API request with username:', username);
            
            const response = await fetch('/api/activate_trial', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ username: username })
            });
            
            console.log('🎁 [TRIAL] API response status:', response.status);
            
            const data = await response.json();
            console.log('🎁 [TRIAL] API response data:', data);
            
            if (data.success) {
                console.log('🎉 [TRIAL] Trial activated successfully');
                
                // Show confirmation modal instead of just toast
                this.showTrialConfirmationModal(username, data);
                
                // Hide trial button immediately
                if (trialBtn) {
                    trialBtn.style.display = 'none';
                }
                const trialInfo = document.getElementById('trial-info');
                if (trialInfo) {
                    trialInfo.style.display = 'none';
                }
                
                // Auto-fill the username in both forms for user convenience
                const discoveryEmail = document.getElementById('discovery-email');
                const keywordEmail = document.getElementById('keyword-email');
                
                if (discoveryEmail) {
                    discoveryEmail.value = username;
                }
                if (keywordEmail) {
                    keywordEmail.value = username;
                }
                
                // Update subscription info and UI - Force refresh with delay
                console.log('🔄 [TRIAL] Refreshing subscription status...');
                
                // Small delay to ensure backend has processed the trial
                setTimeout(async () => {
                    await this.checkSubscription(username, 'discovery');
                    console.log('✅ [TRIAL] Subscription status refreshed after delay');
                    
                    // Also update the userSubscriptionInfo for immediate use
                    this.userSubscriptionInfo = {
                        tier: 'basic',
                        max_fans: 25,
                        status: 'active',
                        trial_used: true,
                        is_trial: true
                    };
                    
                    // Set flag to prevent upgrade modal for next 10 seconds
                    this.recentTrialActivation = true;
                    setTimeout(() => {
                        this.recentTrialActivation = false;
                    }, 10000); // 10 seconds grace period
                    
                    // Update input limits immediately
                    this.updateInputLimitsForTrial(username);
                }, 1000);
            } else {
                console.log('❌ [TRIAL] Trial activation failed:', data.message);
                this.showToast(`❌ ${data.message}`, 'error', 8000);
            }
        } catch (error) {
            console.error('❌ [TRIAL] Trial activation error:', error);
            this.showToast('❌ Error activating trial. Please try again.', 'error');
        } finally {
            // Reset button state
            if (trialBtn) {
                trialBtn.disabled = false;
                trialBtn.innerHTML = '<i class="fas fa-gift me-2"></i>Start 1-Day Free Trial';
            }
        }
    }
    
    updateInputLimitsForTrial(username) {
        // Update input limits and placeholders for trial users
        ['discovery', 'keyword'].forEach(scriptType => {
            const targetInput = document.getElementById(`${scriptType}-target-users`);
            if (targetInput) {
                targetInput.max = 25;
                targetInput.placeholder = `Max 25 fans (basic trial)`;
                
                // If the current value exceeds 25, set it to 25
                if (parseInt(targetInput.value) > 25) {
                    targetInput.value = 25;
                }
                
                console.log(`🔧 [TRIAL] Updated ${scriptType} input limits for trial user`);
            }
        });
    }
    
    showTrialConfirmationModal(username, data) {
        // Create confirmation modal
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.setAttribute('tabindex', '-1');
        
        modal.innerHTML = `
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content border-0 shadow-lg">
                    <!-- Header -->
                    <div class="modal-header border-0 text-center" style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white;">
                        <div class="w-100 text-center">
                            <div class="mb-2">
                                <i class="fas fa-check-circle fa-3x"></i>
                            </div>
                            <h4 class="mb-1 fw-bold">Free Trial Activated!</h4>
                            <small class="opacity-90">Your 24-hour trial has started</small>
                        </div>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    
                    <!-- Body -->
                    <div class="modal-body text-center p-4">
                        <div class="alert alert-success border-0 bg-success bg-opacity-10 mb-4">
                            <div class="d-flex align-items-center justify-content-center">
                                <i class="fas fa-user-check text-success me-3 fa-2x"></i>
                                <div>
                                    <h6 class="mb-1 fw-bold text-success">Trial Active for "${username}"</h6>
                                    <small class="text-muted">You now have basic plan access (25 Target Fans)</small>
                                </div>
                            </div>
                        </div>
                        
                        <div class="row text-start">
                            <div class="col-6">
                                <h6 class="fw-bold text-primary"><i class="fas fa-clock me-2"></i>Duration</h6>
                                <p class="mb-3">24 hours</p>
                            </div>
                            <div class="col-6">
                                <h6 class="fw-bold text-primary"><i class="fas fa-users me-2"></i>Target Fans</h6>
                                <p class="mb-3">Up to 25 fans</p>
                            </div>
                        </div>
                        
                        <div class="alert alert-info border-0 bg-primary bg-opacity-10">
                            <h6 class="fw-bold text-primary mb-2">
                                <i class="fas fa-lightbulb me-2"></i>Ready to Start!
                            </h6>
                            <p class="mb-0">
                                Your username has been automatically filled in the Discovery Search and Keyword Search forms. 
                                You can now start using Fan Finder with your trial subscription!
                            </p>
                        </div>
                        
                        <div class="text-muted mt-3">
                            <small>
                                <i class="fas fa-info-circle me-1"></i>
                                Trial expires: ${data.trial_end || 'in 24 hours'}
                            </small>
                        </div>
                    </div>
                    
                    <!-- Footer -->
                    <div class="modal-footer border-0 bg-light">
                        <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">
                            <i class="fas fa-times me-2"></i>Close
                        </button>
                        <button type="button" class="btn btn-primary fw-bold" onclick="document.getElementById('discovery-tab').click(); bootstrap.Modal.getInstance(this.closest('.modal')).hide();">
                            <i class="fas fa-arrow-right me-2"></i>Proceed
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        const modalInstance = new bootstrap.Modal(modal);
        modalInstance.show();
        
        // Clean up modal after closing
        modal.addEventListener('hidden.bs.modal', () => {
            document.body.removeChild(modal);
        });
    }

    showSubscriptionModal(data) {
        const modal = new bootstrap.Modal(document.getElementById('subscriptionModal'));
        const content = document.getElementById('subscription-content');
        
        let html = `
            <div class="alert alert-warning">
                <i class="fas fa-exclamation-triangle me-2"></i>
                <strong>${data.message}</strong>
            </div>
        `;
        
        if (data.subscription_info && data.subscription_info.status === 'expired') {
            html += `
                <div class="alert alert-info">
                    <h6><i class="fas fa-clock me-2"></i>Subscription Expired</h6>
                    <p>Your subscription expired on: <strong>${data.subscription_info.subscription_end}</strong></p>
                    <p>Please renew your subscription to continue using the service.</p>
                </div>
            `;
        }
        
        if (data.payment_info) {
            // Use dynamic pricing and payment details if available
            const displayPrice = this.currentPricing ? 
                this.currentPricing.monthly_price : 
                data.payment_info.price;
            const displayCurrency = this.currentPricing ? 
                this.currentPricing.currency : 
                'EUR';
            const displayIban = this.currentPaymentDetails ?
                this.currentPaymentDetails.iban :
                data.payment_info.iban;
            const displayBic = this.currentPaymentDetails ?
                this.currentPaymentDetails.bic :
                data.payment_info.bic;
            const displayBeneficiary = this.currentPaymentDetails ?
                this.currentPaymentDetails.beneficiary :
                data.payment_info.beneficiary;
            const displayReference = data.payment_info.reference; // Always from server (no USERNAME_ prefix)
            
            // Check payment mode
            const isPending = displayIban === 'PENDING_BUSINESS_VERIFICATION' || 
                             displayIban.includes('PENDING') || 
                             displayBic === 'PENDING';
            // Force manual payment mode for now
            const isManual = true; // this.currentPaymentDetails && 
                           // this.currentPaymentDetails.status === 'manual_verification';
                
            this.paymentDetails = `Amount: ${displayCurrency} ${displayPrice}
IBAN: ${displayIban}
BIC: ${displayBic}
Reference: ${displayReference}
Beneficiary: ${displayBeneficiary}`;
            
            if (isPending) {
                // Show pending state instead of payment details
                html += `
                    <div class="alert alert-warning">
                        <h6><i class="fas fa-clock me-2"></i>Bank Details Coming Soon!</h6>
                        <p class="mb-2">We're setting up international bank details for your convenience.</p>
                        <p class="mb-0"><strong>Status:</strong> Wise business account verification in progress</p>
                    </div>
                    
                    <div class="payment-pending">
                        <h6><i class="fas fa-hourglass-half me-2"></i>Payment Setup Status</h6>
                        <div class="pending-item">
                            <span class="pending-label">API Integration:</span>
                            <span class="badge bg-success">Ready</span>
                        </div>
                        <div class="pending-item">
                            <span class="pending-label">Payment Monitoring:</span>
                            <span class="badge bg-success">Ready</span>
                        </div>
                        <div class="pending-item">
                            <span class="pending-label">International Bank Details:</span>
                            <span class="badge bg-warning">Pending</span>
                        </div>
                    </div>
                    
                    <div class="instructions">
                        <h6><i class="fas fa-info-circle me-2"></i>What's Happening</h6>
                        <ol>
                            <li>Wise business account verification is in progress</li>
                            <li>International bank details (IBAN, BIC) will be available soon</li>
                            <li>Payment system will activate automatically once complete</li>
                            <li>You'll be notified when payments can be accepted</li>
                        </ol>
                        <div class="alert alert-info mt-3">
                            <i class="fas fa-rocket me-2"></i>
                            <strong>Almost Ready:</strong> All backend systems are prepared and will activate 
                            automatically once bank details are available!
                        </div>
                    </div>
                `;
            } else if (isManual) {
                // Show manual verification mode
                html += `
                    <div class="payment-details">
                        <h6><i class="fas fa-credit-card me-2"></i>Payment Details</h6>
                        <div class="payment-item">
                            <span class="payment-label">Amount:</span>
                            <span class="payment-value">${displayCurrency} ${displayPrice}</span>
                        </div>
                        <div class="payment-item">
                            <span class="payment-label">IBAN:</span>
                            <span class="payment-value">${displayIban}</span>
                        </div>
                        <div class="payment-item">
                            <span class="payment-label">BIC:</span>
                            <span class="payment-value">${displayBic}</span>
                        </div>
                        <div class="payment-item">
                            <span class="payment-label">Reference:</span>
                            <span class="payment-value">${displayReference}</span>
                        </div>
                        <div class="payment-item">
                            <span class="payment-label">Beneficiary:</span>
                            <span class="payment-value">${displayBeneficiary}</span>
                        </div>
                        
                        <!-- Copy Payment Details Button -->
                        <div class="d-grid mt-4">
                            <button type="button" class="btn btn-outline-orange" onclick="copyPaymentDetails()">
                                <i class="fas fa-copy me-2"></i>Copy Payment Details
                            </button>
                        </div>
                    </div>
                    
                    <div class="instructions mt-4">
                        <h6><i class="fas fa-info-circle me-2"></i>Manual Payment Process</h6>
                        <ol>
                            <li>Transfer the exact amount to the account above</li>
                            <li>Include your username as the payment reference</li>
                            <li>Wait for verification (within 12 hours)</li>
                            <li>You'll receive confirmation once verified</li>
                        </ol>
                        <div class="alert alert-warning mt-3">
                            <i class="fas fa-clock me-2"></i>
                            <strong>Processing Time:</strong> Payment verification and account activation within 12 hours. Send an email to st.ryzen@outlook.com if your account is not activated after 24 hours.
                        </div>
                    </div>
                    
                    <!-- Payment Screenshot Upload (Optional) -->
                    <div class="payment-upload-section mt-4 p-3 bg-light rounded">
                        <h6><i class="fas fa-upload me-2"></i>Upload Payment Proof (Optional)</h6>
                        <p class="text-muted small">Help us process your payment faster by uploading a screenshot of your transfer.</p>
                        
                        <div class="mb-3">
                            <label for="payment-screenshot" class="form-label">Payment Screenshot</label>
                            <input type="file" class="form-control" id="payment-screenshot" accept="image/*">
                            <div class="form-text">Upload a screenshot of your payment confirmation</div>
                        </div>
                        
                        <div class="mb-3">
                            <label for="payment-note" class="form-label">Note (Optional)</label>
                            <textarea class="form-control" id="payment-note" rows="3" placeholder="Add any additional information about your payment..."></textarea>
                        </div>
                        
                        <button class="btn btn-outline-orange btn-sm" onclick="submitPaymentProof()">
                            <i class="fas fa-paper-plane me-1"></i>Submit Payment Proof
                        </button>
                    </div>
                `;
            } else {
                // Show automated payment details
                html += `
                    <div class="alert alert-success">
                        <h6><i class="fas fa-magic me-2"></i>Smart Payment Detection</h6>
                        <p class="mb-0">Your payment will be automatically detected and your account activated instantly!</p>
                    </div>
                    
                    <div class="payment-details">
                        <h6><i class="fas fa-credit-card me-2"></i>Payment Details</h6>
                        <div class="payment-item">
                            <span class="payment-label">Amount:</span>
                            <span class="payment-value">${displayCurrency} ${displayPrice}</span>
                        </div>
                        <div class="payment-item">
                            <span class="payment-label">IBAN:</span>
                            <span class="payment-value">${displayIban}</span>
                        </div>
                        <div class="payment-item">
                            <span class="payment-label">BIC:</span>
                            <span class="payment-value">${displayBic}</span>
                        </div>
                        <div class="payment-item">
                            <span class="payment-label">Reference:</span>
                            <span class="payment-value">${displayReference}</span>
                        </div>
                        <div class="payment-item">
                            <span class="payment-label">Beneficiary:</span>
                            <span class="payment-value">${displayBeneficiary}</span>
                        </div>
                        
                        <!-- Copy Payment Details Button -->
                        <div class="d-grid mt-4">
                            <button type="button" class="btn btn-outline-orange" onclick="copyPaymentDetails()">
                                <i class="fas fa-copy me-2"></i>Copy Payment Details
                            </button>
                        </div>
                    </div>
                    
                    <!-- Payment Status Tracker -->
                    <div class="payment-tracker mt-4">
                        <h6><i class="fas fa-route me-2"></i>Payment Status</h6>
                        <div class="progress-steps">
                            <div class="step active" id="step-reference">
                                <div class="step-icon"><i class="fas fa-tag"></i></div>
                                <div class="step-text">Reference Generated</div>
                            </div>
                            <div class="step" id="step-payment-sent">
                                <div class="step-icon"><i class="fas fa-paper-plane"></i></div>
                                <div class="step-text">Payment Sent</div>
                            </div>
                            <div class="step" id="step-payment-detected">
                                <div class="step-icon"><i class="fas fa-search"></i></div>
                                <div class="step-text">Payment Detected</div>
                            </div>
                            <div class="step" id="step-account-activated">
                                <div class="step-icon"><i class="fas fa-check-circle"></i></div>
                                <div class="step-text">Account Activated</div>
                            </div>
                        </div>
                        <div class="status-message" id="payment-status-message">
                            <i class="fas fa-clock me-2"></i>Waiting for payment...
                        </div>
                    </div>
                    
                    <div class="instructions">
                        <h6><i class="fas fa-list-ol me-2"></i>Enhanced Payment Instructions</h6>
                        <ol>
                            <li>Transfer <strong>${displayCurrency} ${displayPrice}</strong> to the above bank account</li>
                            <li><strong>IMPORTANT:</strong> Use the exact reference <strong>"${displayReference}"</strong> in your transfer</li>
                            <li>Your payment will be detected automatically within 5 minutes</li>
                            <li>Account will be activated instantly when payment is confirmed</li>
                            <li>You will receive email confirmation once activated</li>
                        </ol>
                        <div class="alert alert-info mt-3">
                            <i class="fas fa-robot me-2"></i>
                            Our system monitors payments automatically. 
                            No need to contact support - your account will activate as soon as payment is received!
                        </div>
                    </div>
                `;
            }
        }
        
        content.innerHTML = html;
        modal.show();
        
        // Start payment status tracking (only for automated mode)
        if (!isPending && !isManual) {
            this.startPaymentTracking(data.payment_info.reference);
        }
    }

    showPlanModal(planType, selectedUsername = null) {
        console.log('[PLAN_MODAL] showPlanModal called with:', planType, 'Username:', selectedUsername);
        console.log('[PLAN_MODAL] currentPricing:', this.currentPricing);
        console.log('[PLAN_MODAL] currentPaymentDetails:', this.currentPaymentDetails);
        
        if (!this.currentPricing || !this.currentPaymentDetails) {
            console.error('[PLAN_MODAL] Missing pricing or payment details');
            this.showToast('Loading pricing information, please try again in a moment...', 'warning');
            
            // Try to load the data and retry
            Promise.all([
                this.loadCurrentPricing(),
                this.loadCurrentPaymentDetails()
            ]).then(() => {
                console.log('[PLAN_MODAL] Data loaded, retrying...');
                setTimeout(() => this.showPlanModal(planType), 500);
            }).catch(error => {
                console.error('[PLAN_MODAL] Failed to load data:', error);
                this.showToast('Failed to load pricing information. Please refresh the page.', 'danger');
            });
            return;
        }

        const modal = new bootstrap.Modal(document.getElementById('subscriptionModal'));
        const content = document.getElementById('subscription-content');
        const modalTitle = document.querySelector('#subscriptionModal .modal-title');
        
        // Calculate plan details
        const monthlyPrice = this.currentPricing.monthly_price;
        const currency = this.currentPricing.currency === 'EUR' ? '€' : this.currentPricing.currency;
        
        let planDetails = {};
        
        switch(planType) {
            case 'monthly':
                planDetails = {
                    title: '1 Month Plan',
                    price: monthlyPrice,
                    originalPrice: null,
                    duration: '1 month',
                    maxFans: '25 fans per search',
                    discount: null,
                    tier: 'Basic'
                };
                break;
            case 'sixmonth':
                planDetails = {
                    title: '6 Months Plan',
                    price: Math.round(monthlyPrice * 6 * 0.7),
                    originalPrice: monthlyPrice * 6,
                    duration: '6 months',
                    maxFans: '100 fans per search',
                    discount: '30% OFF',
                    tier: 'Premium'
                };
                break;
            case 'yearly':
                planDetails = {
                    title: '1 Year Plan',
                    price: Math.round(monthlyPrice * 12 * 0.5),
                    originalPrice: monthlyPrice * 12,
                    duration: '1 year',
                    maxFans: 'Unlimited fans per search',
                    discount: '50% OFF',
                    tier: 'Enterprise'
                };
                break;
        }

        // Update modal title and subtitle
        document.getElementById('modal-plan-title').innerHTML = planDetails.title;
        document.getElementById('modal-plan-subtitle').innerHTML = `${planDetails.tier} • Up to ${planDetails.maxFans}`;

        // Generate payment reference (clean username without prefix)
        let username = '';
        if (selectedUsername) {
            // Use the username from the modal
            username = selectedUsername;
        } else {
            // Fallback to form fields for backwards compatibility
            const discoveryUsername = document.getElementById('discovery-username')?.value?.trim() || '';
            const keywordUsername = document.getElementById('keyword-username')?.value?.trim() || '';
            username = discoveryUsername || keywordUsername || '';
        }
        const hasUsername = username.length > 0;
        const reference = hasUsername ? username : '[ENTER_YOUR_USERNAME]';

        // Store payment details for copy function
        this.paymentDetails = `Amount: ${currency} ${planDetails.price}
IBAN: ${this.currentPaymentDetails.iban}
BIC: ${this.currentPaymentDetails.bic}
Reference: ${reference}
Beneficiary: ${this.currentPaymentDetails.beneficiary}`;

        let html = `
            <!-- Plan Overview Card -->
            <div class="plan-features p-4 mb-4">
                <div class="row align-items-center">
                    <div class="col-md-8">
                        <h5 class="fw-bold mb-3" style="color: #ff6b35;">
                            <i class="fas fa-star me-2"></i>${planDetails.title} Features
                        </h5>
                        <div class="row">
                            <div class="col-6">
                                <div class="feature-item">
                                    <i class="fas fa-check-circle text-success me-2"></i>
                                    <span>Discovery Search</span>
                                </div>
                                <div class="feature-item">
                                    <i class="fas fa-check-circle text-success me-2"></i>
                                    <span>Real-time Progress</span>
                                </div>
                            </div>
                            <div class="col-6">
                                <div class="feature-item">
                                    <i class="fas fa-check-circle text-success me-2"></i>
                                    <span>Keyword Search</span>
                                </div>
                                <div class="feature-item">
                                    <i class="fas fa-check-circle text-success me-2"></i>
                                    <span>Browser Automation</span>
                                </div>
                            </div>
                        </div>
                        <div class="feature-item mt-2">
                            <i class="fas fa-users me-2" style="color: #ff6b35;"></i>
                            <strong>Maximum ${planDetails.maxFans}</strong>
                        </div>
                    </div>
                    <div class="col-md-4 text-center">
                        <div class="pricing-display">
                            ${planDetails.originalPrice ? `<div class="text-muted text-decoration-line-through mb-1">${currency} ${planDetails.originalPrice}</div>` : ''}
                            <div class="display-6 fw-bold" style="color: #ff6b35;">${currency} ${planDetails.price}</div>
                            <small class="text-muted">for ${planDetails.duration}</small>
                            ${planDetails.discount ? `<div class="badge bg-success mt-2">${planDetails.discount}</div>` : ''}
                        </div>
                    </div>
                </div>
            </div>

            <!-- Payment Details Card -->
            <div class="payment-card p-4 mb-4">
                <h5 class="fw-bold mb-3">
                    <i class="fas fa-credit-card me-2" style="color: #ff6b35;"></i>Payment Details
                </h5>
                <div class="payment-detail-item">
                    <span class="payment-label">Amount</span>
                    <span class="payment-value fw-bold" style="color: #ff6b35;">${currency} ${planDetails.price}</span>
                </div>
                <div class="payment-detail-item">
                    <span class="payment-label">IBAN</span>
                    <span class="payment-value font-monospace">${this.currentPaymentDetails.iban}</span>
                </div>
                <div class="payment-detail-item">
                    <span class="payment-label">BIC</span>
                    <span class="payment-value font-monospace">${this.currentPaymentDetails.bic}</span>
                </div>
                <div class="payment-detail-item">
                    <span class="payment-label">Reference</span>
                    <span class="payment-value fw-bold ${hasUsername ? 'text-success' : 'text-warning'}">${reference}</span>
                </div>
                <div class="payment-detail-item">
                    <span class="payment-label">Beneficiary</span>
                    <span class="payment-value">${this.currentPaymentDetails.beneficiary}</span>
                </div>
                ${!hasUsername ? '<div class="alert alert-warning mt-3 mb-0"><i class="fas fa-exclamation-triangle me-2"></i><small>Please enter your Maloum username in Discovery or Keyword Search tab first</small></div>' : ''}
                
                <!-- Copy Payment Details Button -->
                <div class="d-grid mt-4">
                    <button type="button" class="btn btn-outline-orange" onclick="copyPaymentDetails()">
                        <i class="fas fa-copy me-2"></i>Copy Payment Details
                    </button>
                </div>
            </div>

            <!-- Payment Instructions -->
            <div class="steps-container mb-4">
                <h5 class="fw-bold mb-4">
                    <i class="fas fa-list-ol me-2" style="color: #ff6b35;"></i>Payment Instructions
                </h5>
                ${!hasUsername ? '<div class="alert alert-info mb-3"><i class="fas fa-user me-2"></i><strong>First:</strong> Enter your Maloum username in Discovery or Keyword Search tab to generate your payment reference</div>' : ''}
                <div class="step-item">
                    <div class="step-number">1</div>
                    <div>
                        <strong>Open your banking app</strong>
                        <div class="text-muted small">Use mobile banking or visit your bank</div>
                    </div>
                </div>
                <div class="step-item">
                    <div class="step-number">2</div>
                    <div>
                        <strong>Make transfer: ${currency} ${planDetails.price}</strong>
                        <div class="text-muted small">Transfer the exact amount shown</div>
                    </div>
                </div>
                <div class="step-item">
                    <div class="step-number">3</div>
                    <div>
                        <strong>Use reference: ${reference}</strong>
                        <div class="text-muted small">This activates your subscription</div>
                    </div>
                </div>
                <div class="step-item">
                    <div class="step-number">4</div>
                    <div>
                        <strong>Wait for activation</strong>
                        <div class="text-muted small">Within 12 hours of payment</div>
                    </div>
                </div>
            </div>`; // Close the steps-container

        // Add payment proof submission section
        html += `
            <!-- Payment Proof Submission -->
            <div class="payment-proof-section p-4 mt-4 border-top">
                <h5 class="fw-bold mb-3">
                    <i class="fas fa-receipt me-2" style="color: #ff6b35;"></i>Submit Payment Proof
                </h5>
                <p class="text-muted small mb-3">
                    After making your payment, upload a screenshot of the transaction and add a note for faster processing.
                </p>
                
                <form id="payment-proof-form" class="payment-proof-form">
                    <input type="hidden" id="payment-proof-username" name="username" value="${username}">
                    <input type="hidden" id="payment-proof-timestamp" name="timestamp" value="${new Date().toISOString()}">
                    
                    <div class="mb-3">
                        <label for="payment-proof-note" class="form-label">Note (Optional)</label>
                        <textarea class="form-control" id="payment-proof-note" name="note" rows="2" 
                                  placeholder="Add any additional information about your payment..."></textarea>
                    </div>
                    
                    <div class="mb-3">
                        <label for="payment-proof-screenshot" class="form-label">Screenshot</label>
                        <input type="file" class="form-control" id="payment-proof-screenshot" name="screenshot" 
                               accept="image/*" capture="environment">
                        <div class="form-text">Upload a screenshot of your payment confirmation</div>
                    </div>
                    
                    <div class="d-grid">
                        <button type="button" class="btn btn-success" onclick="submitPaymentProof()">
                            <i class="fas fa-paper-plane me-2"></i>Submit Payment Proof
                        </button>
                    </div>
                </form>
            </div>`;

        content.innerHTML = html;
        modal.show();
    }

    startPaymentTracking(reference) {
        if (this.paymentTrackingInterval) {
            clearInterval(this.paymentTrackingInterval);
        }

        console.log(`🔍 Starting payment tracking for reference: ${reference}`);
        
        // Check payment status every 30 seconds
        this.paymentTrackingInterval = setInterval(async () => {
            try {
                const response = await fetch('/api/payment-status', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ reference: reference })
                });

                if (response.ok) {
                    const status = await response.json();
                    this.updatePaymentStatus(status);
                }
            } catch (error) {
                console.error('Payment status check failed:', error);
            }
        }, 30000); // Check every 30 seconds

        // Also check immediately
        this.checkPaymentStatusOnce(reference);
    }

    async checkPaymentStatusOnce(reference) {
        try {
            const response = await fetch('/api/payment-status', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ reference: reference })
            });

            if (response.ok) {
                const status = await response.json();
                this.updatePaymentStatus(status);
            }
        } catch (error) {
            console.error('Immediate payment status check failed:', error);
        }
    }

    updatePaymentStatus(status) {
        const steps = {
            'payment-sent': 'step-payment-sent',
            'payment-detected': 'step-payment-detected', 
            'account-activated': 'step-account-activated'
        };

        const messages = {
            'waiting': '⏳ Waiting for payment...',
            'payment-sent': '📤 Payment sent - monitoring for confirmation...',
            'payment-detected': '✅ Payment detected! Activating account...',
            'account-activated': '🎉 Account activated successfully!'
        };

        // Update visual steps
        if (status.step && steps[status.step]) {
            const stepElement = document.getElementById(steps[status.step]);
            if (stepElement && !stepElement.classList.contains('active')) {
                stepElement.classList.add('active');
                
                // Show success toast
                if (status.step === 'payment-detected') {
                    this.showToast('Payment detected! Activating your account...', 'success', 5000);
                } else if (status.step === 'account-activated') {
                    this.showToast('Account activated successfully!', 'success', 5000);
                    
                    // Stop tracking and reload page after delay
                    if (this.paymentTrackingInterval) {
                        clearInterval(this.paymentTrackingInterval);
                    }
                    
                    setTimeout(() => {
                        window.location.reload();
                    }, 3000);
                }
            }
        }

        // Update status message
        const messageElement = document.getElementById('payment-status-message');
        if (messageElement && status.status && messages[status.status]) {
            messageElement.innerHTML = `<i class="fas fa-clock me-2"></i>${messages[status.status]}`;
        }
    }
    
    updateConnectionStatus(status) {
        const statusEl = document.getElementById('connection-status');
        if (!statusEl) {
            console.error('❌ connection-status element not found!');
            return;
        }
        
        const statusClasses = ['alert-info', 'alert-success', 'alert-danger'];
        
        // Remove all status classes
        statusClasses.forEach(cls => statusEl.classList.remove(cls));
        
        switch (status) {
            case 'connecting':
                statusEl.style.display = 'flex';
                statusEl.classList.add('alert-info');
                statusEl.innerHTML = `
                    <div class="spinner-border spinner-border-sm me-2" role="status"></div>
                    <span>Connecting to server...</span>
                `;
                break;
            case 'connected':
                console.log('🔧 Hiding connection status - connected successfully');
                // Hide immediately when connected - no success message shown
                statusEl.style.setProperty('display', 'none', 'important');
                statusEl.classList.add('d-none');
                statusEl.setAttribute('hidden', 'true');
                console.log('🔧 Connection status should be hidden now');
                
                // Double-check after a brief delay to ensure it stays hidden
                setTimeout(() => {
                    if (statusEl && this.isConnected) {
                        statusEl.style.setProperty('display', 'none', 'important');
                        statusEl.classList.add('d-none');
                        statusEl.setAttribute('hidden', 'true');
                        console.log('🔧 Double-check: Connection status re-hidden');
                    }
                }, 100);
                break;
            case 'reconnecting':
                statusEl.style.display = 'flex';
                statusEl.classList.add('alert-info');
                statusEl.innerHTML = `
                    <div class="spinner-border spinner-border-sm me-2" role="status"></div>
                    <span>Reconnecting to server...</span>
                `;
                break;
            case 'disconnected':
            case 'error':
                statusEl.style.display = 'flex';
                statusEl.classList.add('alert-danger');
                statusEl.innerHTML = `
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    <span>Connection lost. Please make sure the server is running.</span>
                `;
                break;
        }
    }
    
    updateScriptStatus(scriptType, status) {
        this.scriptStatus[scriptType] = status;

        const indicator = document.getElementById(`${scriptType}-status-indicator`);
        const text = document.getElementById(`${scriptType}-status-text`);
        const info = document.getElementById(`${scriptType}-info`);
        const startBtn = document.getElementById(`${scriptType}-start-btn`);
        const stopBtn = document.getElementById(`${scriptType}-stop-btn`);
        const progressBar = document.getElementById(`${scriptType}-progress`);

        // Add null checks for old UI elements (new instance-based UI doesn't have these)
        if (!indicator || !text || !info) {
            console.log(`⚠️  Status elements not found for ${scriptType} - using new instance-based UI`);
            return;
        }

        // Remove all status classes
        indicator.className = 'status-indicator me-2';

        console.log(`🔄 Updating ${scriptType} status to: ${status}`);

        switch (status) {
            case 'ready':
                indicator.classList.add('status-ready');
                text.textContent = 'Ready';
                info.textContent = '';
                if (startBtn) startBtn.style.display = 'inline-block';
                if (startBtn) startBtn.disabled = false;
                if (stopBtn) stopBtn.style.display = 'none';
                // Remove all scanning animations
                if (progressBar) {
                    progressBar.classList.remove('progress-bar-animated', 'progress-bar-striped', 'scanning');
                    progressBar.removeAttribute('data-scanning');
                    progressBar.style.width = '0%';
                }
                break;
                
            case 'starting':
                indicator.classList.add('status-running');
                text.textContent = 'Starting...';
                info.textContent = 'Initializing script...';
                if (startBtn) startBtn.style.display = 'none';
                if (stopBtn) stopBtn.style.display = 'inline-block';
                if (stopBtn) stopBtn.disabled = false;
                // IMMEDIATELY start scanning animation
                if (progressBar) {
                    console.log(`🎬 Starting scanning animation for ${scriptType}`);
                    progressBar.classList.add('progress-bar-animated', 'progress-bar-striped', 'scanning');
                    progressBar.style.width = '100%'; // Full width for scanning
                    progressBar.setAttribute('data-scanning', 'true'); // Light color for scanning
                    
                    const progressText = progressBar.querySelector('span');
                    if (progressText) {
                        const target = parseInt(document.getElementById(`${scriptType}-target-users`).value) || 0;
                        progressText.textContent = `Initializing... (0/${target} users)`;
                    }
                }
                break;
                
            case 'running':
                indicator.classList.add('status-running');
                text.textContent = 'Running';
                info.textContent = 'Script is active and scanning...';
                if (startBtn) startBtn.style.display = 'none';
                if (stopBtn) stopBtn.style.display = 'inline-block';
                if (stopBtn) stopBtn.disabled = false;
                // Ensure scanning animation continues
                if (progressBar) {
                    console.log(`🎬 Ensuring scanning animation continues for ${scriptType}`);
                    progressBar.classList.add('progress-bar-animated', 'progress-bar-striped', 'scanning');
                    // Keep full width scanning until users are found
                    if (!progressBar.getAttribute('data-scanning') || progressBar.getAttribute('data-scanning') === 'true') {
                        progressBar.style.width = '100%';
                        progressBar.setAttribute('data-scanning', 'true');
                    }
                }
                break;
                
            case 'stopping':
                indicator.classList.add('status-running');
                text.textContent = 'Stopping...';
                info.textContent = 'Terminating script and closing browser...';
                if (startBtn) startBtn.style.display = 'none';
                if (stopBtn) stopBtn.style.display = 'inline-block';
                if (stopBtn) stopBtn.disabled = true;
                // Keep animation until fully stopped
                setTimeout(() => { 
                    if (stopBtn) stopBtn.disabled = false; 
                }, 5000);
                break;
                
            case 'blocked':
                indicator.classList.add('status-error');
                text.textContent = 'Not Ready';
                info.textContent = 'Another script is running';
                if (startBtn) startBtn.style.display = 'inline-block';
                if (startBtn) startBtn.disabled = true;
                if (stopBtn) stopBtn.style.display = 'none';
                // Remove animation for blocked scripts
                if (progressBar) {
                    progressBar.classList.remove('progress-bar-animated', 'progress-bar-striped', 'scanning');
                    progressBar.removeAttribute('data-scanning');
                }
                break;
                
            case 'error':
                indicator.classList.add('status-error');
                text.textContent = 'Error';
                info.textContent = 'Check logs for details';
                if (startBtn) startBtn.style.display = 'inline-block';
                if (startBtn) startBtn.disabled = false;
                if (stopBtn) stopBtn.style.display = 'none';
                // Remove animation for errors
                if (progressBar) {
                    progressBar.classList.remove('progress-bar-animated', 'progress-bar-striped', 'scanning');
                    progressBar.removeAttribute('data-scanning');
                }
                break;
        }
    }

    updateProgress(scriptType, data) {
        console.log(`[${scriptType.toUpperCase()}] Updating Progress Bar:`, data);

        const progress = Math.round(data.progress || 0);
        const collected = data.collected_users || 0;
        const target = data.target_users || 0;

        // Update instance progress bars if window function is available
        if (window.updateInstanceProgress) {
            const instanceNumber = data.instance_number || 1;
            window.updateInstanceProgress(scriptType, progress, collected, target, instanceNumber);
            return; // Use instance-specific progress bars, skip old global progress bar
        }

        // Fallback for old global progress bar elements (if they exist)
        const progressBar = document.getElementById(`${scriptType}-progress`);
        const info = document.getElementById(`${scriptType}-info`);

        if (!progressBar || !info) {
            console.warn(`Progress elements not found for ${scriptType}`);
            return;
        }
        
        // Update progress bar text
        const progressText = progressBar.querySelector('span');
        if (progressText) {
            if (this.scriptStatus[scriptType] === 'running' || this.scriptStatus[scriptType] === 'starting') {
                if (progress > 0 && collected > 0) {
                    // Show actual progress percentage - use Math.round to avoid 0%
                    const displayProgress = Math.max(1, Math.round(progress)); // Minimum 1% when progress > 0
                    progressText.textContent = `${collected}/${target} users (${displayProgress}%)`;
                } else {
                    progressText.textContent = `Scanning... (${collected}/${target} users)`;
                }
            } else {
                const displayProgress = Math.round(progress);
                progressText.textContent = `${collected}/${target} users (${displayProgress}%)`;
            }
            console.log(`[${scriptType.toUpperCase()}] Updated progress text: "${progressText.textContent}"`);
        }
        
        // Handle progress bar width and animation
        if (this.scriptStatus[scriptType] === 'running' || this.scriptStatus[scriptType] === 'starting') {
            // Script is running - show scanning animation
            progressBar.classList.add('progress-bar-animated', 'progress-bar-striped', 'scanning');
            
            if (progress > 0 && collected > 0) {
                // Show actual progress with scanning animation on top
                progressBar.style.width = `${Math.max(progress, 10)}%`; // Minimum 10% to show animation
                progressBar.setAttribute('data-scanning', 'false');
                console.log(`[${scriptType.toUpperCase()}] Showing progress: ${progress}% with scanning animation`);
            } else {
                // No progress yet - show full-width scanning animation with lighter color
                progressBar.style.width = '100%';
                progressBar.setAttribute('data-scanning', 'true');
                console.log(`[${scriptType.toUpperCase()}] Showing full-width scanning animation`);
            }
        } else {
            // Script not running - remove animation and show actual progress
            progressBar.classList.remove('progress-bar-animated', 'progress-bar-striped', 'scanning');
            progressBar.style.width = `${progress}%`;
            progressBar.removeAttribute('data-scanning');
        }
        
        progressBar.setAttribute('aria-valuenow', progress);
        
        // Update info text
        if (progress === 100) {
            info.textContent = `✅ Completed! Found ${collected} users`;
            info.className = 'text-success fw-bold';
            // Remove scanning when complete
            progressBar.classList.remove('scanning', 'progress-bar-animated', 'progress-bar-striped');
            progressBar.removeAttribute('data-scanning');
        } else if (this.scriptStatus[scriptType] === 'running' || this.scriptStatus[scriptType] === 'starting') {
            if (progress > 0 && collected > 0) {
                info.textContent = `🔍 Collecting users... ${collected}/${target} found`;
            } else {
                info.textContent = '🔄 Initializing and scanning for users...';
            }
            info.className = 'text-primary';
        } else {
            info.textContent = 'Ready to start';
            info.className = 'text-muted';
        }
    }
    
    checkForNewUser(scriptType, message, timestamp) {
        // Debug: Log all messages to see what we're getting
        console.log(`[${scriptType.toUpperCase()}] Processing: "${message}"`);
        
        // Look for EXACT patterns from your logs
        const userPatterns = [
            // Match "[SUCCESS] Collected user: romario69 (1/300 - 0.3%)"
            /\[SUCCESS\]\s+Collected user:\s+([^\s(]+)\s+\(\d+\/\d+\s*-\s*[\d.]+%\)/i,
            
            // Match without [SUCCESS] prefix
            /Collected user:\s+([^\s(]+)\s+\(\d+\/\d+\s*-\s*[\d.]+%\)/i,
            
            // Match "[SUCCESS] New user found: username (1/300 - 0.3%)"
            /\[SUCCESS\]\s+New user found:\s+([^\s(]+)\s+\(\d+\/\d+\s*-\s*[\d.]+%\)/i,
            
            // Match without [SUCCESS] prefix
            /New user found:\s+([^\s(]+)\s+\(\d+\/\d+\s*-\s*[\d.]+%\)/i,
        ];
        
        // Check each pattern
        for (let i = 0; i < userPatterns.length; i++) {
            const pattern = userPatterns[i];
            const match = message.match(pattern);
            if (match) {
                const username = match[1].trim();
                
                if (username && username.length > 0 && username.length < 50) {
                    console.log(`[${scriptType.toUpperCase()}] ✅ DETECTED USER: "${username}" using pattern ${i + 1}`);
                    
                    // Add the user immediately
                    this.addCollectedUser(scriptType, username, timestamp);
                    
                    // Extract progress information from the same message
                    const progressMatch = message.match(/\((\d+)\/(\d+)\s*-\s*([\d.]+)%\)/);
                    if (progressMatch) {
                        const collected = parseInt(progressMatch[1]);
                        const target = parseInt(progressMatch[2]);
                        const progress = parseFloat(progressMatch[3]);
                        
                        console.log(`[${scriptType.toUpperCase()}] 📊 PROGRESS DETECTED: ${collected}/${target} (${progress}%)`);
                        
                        // Update progress immediately
                        this.updateProgress(scriptType, {
                            collected_users: collected,
                            target_users: target,
                            progress: progress
                        });
                    }
                    
                    return; // Exit after first match
                } else {
                    console.log(`[${scriptType.toUpperCase()}] ❌ Invalid username: "${username}"`);
                }
            }
        }
        
        // If no user found, still check for progress updates
        const progressMatch = message.match(/\((\d+)\/(\d+)\s*-\s*([\d.]+)%\)/);
        if (progressMatch) {
            const collected = parseInt(progressMatch[1]);
            const target = parseInt(progressMatch[2]);
            const progress = parseFloat(progressMatch[3]);
            
            console.log(`[${scriptType.toUpperCase()}] 📊 STANDALONE PROGRESS: ${collected}/${target} (${progress}%)`);
            
            this.updateProgress(scriptType, {
                collected_users: collected,
                target_users: target,
                progress: progress
            });
        }
    }

    updateUserProgress(scriptType) {
        // Get current collected count
        const collectedCount = this.collectedUsers[scriptType].length;

        // Get target from form (with null check)
        const targetElement = document.getElementById(`${scriptType}-target-users`);
        const targetUsers = targetElement ? parseInt(targetElement.value) || 0 : 0;

        // Calculate progress
        const progress = targetUsers > 0 ? Math.min(100, (collectedCount / targetUsers) * 100) : 0;

        console.log(`[${scriptType.toUpperCase()}] Progress Update: ${collectedCount}/${targetUsers} users (${progress.toFixed(1)}%)`);

        // Update progress immediately
        this.updateProgress(scriptType, {
            collected_users: collectedCount,
            target_users: targetUsers,
            progress: progress
        });
    }

    addCollectedUser(scriptType, username, timestamp) {
        // Avoid duplicates
        if (this.collectedUsers[scriptType].some(user => user.username === username)) {
            console.log(`[${scriptType.toUpperCase()}] ⚠️ Duplicate user ignored: ${username}`);
            return;
        }
        
        const userObj = {
            username: username,
            timestamp: timestamp,
            id: Date.now() + Math.random()
        };
        
        this.collectedUsers[scriptType].push(userObj);
        console.log(`[${scriptType.toUpperCase()}] ➕ ADDED USER: ${username} (Total: ${this.collectedUsers[scriptType].length})`);
        
        // IMMEDIATELY update the UI
        this.updateUsersDisplay(scriptType);
        
        // IMMEDIATELY update progress
        this.updateUserProgress(scriptType);
        
        console.log(`✅ Added new user for ${scriptType}: ${username}`);
    }

    updateUsersDisplay(scriptType) {
        const container = document.getElementById(`${scriptType}-users-container`);
        const countBadge = document.getElementById(`${scriptType}-user-count`);

        if (!container || !countBadge) {
            console.debug(`Users container not found for ${scriptType} (using instance-based UI)`);
            return;
        }
        
        const users = this.collectedUsers[scriptType];
        
        console.log(`[${scriptType.toUpperCase()}] Updating users display with ${users.length} users`);
        
        // Update count badge
        countBadge.textContent = `${users.length} user${users.length !== 1 ? 's' : ''}`;
        
        if (users.length === 0) {
            container.innerHTML = '<div class="text-muted text-center p-3">No users collected yet...</div>';
            return;
        }
        
        // Clear container
        container.innerHTML = '';
        
        // Add users (most recent first)
        const recentUsers = [...users].reverse().slice(0, 100); // Show only last 100 users
        
        recentUsers.forEach((user, index) => {
            const userItem = document.createElement('div');
            userItem.className = 'user-item';
            if (index === 0) {
                userItem.classList.add('new'); // Animate the newest user
            }
            
            userItem.innerHTML = `
                <span class="user-name">
                    <i class="fas fa-user me-2"></i>${user.username}
                </span>
                <span class="user-timestamp">${user.timestamp}</span>
            `;
            
            container.appendChild(userItem);
        });
        
        // Auto-scroll to top to show newest users
        container.scrollTop = 0;
        
        console.log(`[${scriptType.toUpperCase()}] Users display updated with ${recentUsers.length} visible users`);
    }
    
    clearCollectedUsers(scriptType) {
        this.collectedUsers[scriptType] = [];
        this.updateUsersDisplay(scriptType);
        console.log(`Cleared collected users for ${scriptType}`);
    }
    
    showToast(message, type, duration = 5000) {
        const toastContainer = document.getElementById('toast-container');
        
        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast align-items-center bg-${type} text-white border-0 slide-in`;
        toast.setAttribute('role', 'alert');
        
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    <i class="fas fa-${this.getToastIcon(type)} me-2"></i>
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" 
                        data-bs-dismiss="toast"></button>
            </div>
        `;
        
        toastContainer.appendChild(toast);
        
        // Initialize and show toast
        const bsToast = new bootstrap.Toast(toast, {
            autohide: true,
            delay: duration
        });
        
        bsToast.show();
        
        // Remove toast element after it's hidden
        toast.addEventListener('hidden.bs.toast', () => {
            toast.remove();
        });
    }
    
    getToastIcon(type) {
        switch (type) {
            case 'success': return 'check-circle';
            case 'danger': return 'exclamation-triangle';
            case 'warning': return 'exclamation-circle';
            case 'info': return 'info-circle';
            default: return 'bell';
        }
    }

    // Authentication Methods
    checkAuthentication() {
        const token = sessionStorage.getItem('fanfinder_auth_token');
        const user = sessionStorage.getItem('fanfinder_user');
        
        if (!token || !user) {
            this.redirectToAuth();
            return false;
        }
        
        // Store user data
        try {
            this.currentUser = JSON.parse(user);
            console.log('🔐 Authenticated user:', this.currentUser.username);
            
            // Validate token with server (async)
            this.validateTokenWithServer(token);
            
            // Show user info in header
            this.displayUserInfo();
            
            return true;
        } catch (e) {
            console.error('🔐 Authentication error:', e);
            this.redirectToAuth();
            return false;
        }
    }
    
    async validateTokenWithServer(token) {
        try {
            const response = await fetch('/api/auth/validate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ token })
            });
            
            const data = await response.json();
            
            if (!data.valid) {
                console.log('🔐 Token invalid, redirecting to auth');
                this.signOut();
            } else {
                console.log('🔐 Token validated successfully');
            }
        } catch (error) {
            console.error('🔐 Token validation failed:', error);
            // Don't sign out on network error, allow offline usage
        }
    }
    
    redirectToAuth() {
        window.location.href = '/';
    }
    
    displayUserInfo() {
        // Add user info to the header
        const userInfoContainer = document.createElement('div');
        userInfoContainer.className = 'user-info d-flex align-items-center ms-auto';

        // Create user dropdown
        const userDropdown = document.createElement('div');
        userDropdown.className = 'dropdown';
        userDropdown.innerHTML = `
            <button class="btn btn-outline-light btn-sm dropdown-toggle" type="button" id="userDropdown" data-bs-toggle="dropdown" aria-expanded="false">
                <i class="fas fa-user me-2"></i>${this.currentUser.username}
            </button>
            <ul class="dropdown-menu dropdown-menu-end" aria-labelledby="userDropdown">
                <li><h6 class="dropdown-header">Account</h6></li>
                <li><span class="dropdown-item-text small text-muted">${this.currentUser.username}</span></li>
                <li><hr class="dropdown-divider"></li>
                <li><button class="dropdown-item" onclick="window.app.signOut()"><i class="fas fa-sign-out-alt me-2"></i>Sign Out</button></li>
            </ul>
        `;

        // Add user dropdown to container
        userInfoContainer.appendChild(userDropdown);

        // Find the header navbar and add user info
        const navbarRight = document.querySelector('.navbar .d-flex.align-items-center');
        if (navbarRight) {
            navbarRight.appendChild(userInfoContainer);
        }
    }
    
    signOut() {
        // Clear authentication data from sessionStorage
        sessionStorage.removeItem('fanfinder_auth_token');
        sessionStorage.removeItem('fanfinder_user');

        // Also clear old localStorage auth data if it exists (for migration)
        localStorage.removeItem('fanfinder_auth_token');
        localStorage.removeItem('fanfinder_user');

        // Show sign out message
        console.log('🔐 User signed out');
        
        // Redirect to auth page
        this.redirectToAuth();
    }
    
    async syncAirtableData() {
        console.log('🔄 Starting AirTable sync operation...');
        
        // Get reference to sync status element
        const syncStatus = document.getElementById('sync-status');
        if (syncStatus) {
            syncStatus.innerHTML = '<div class="alert alert-info"><i class="fas fa-spinner fa-spin me-2"></i>Starting sync operation...</div>';
        }
        
        this.showToast('Starting AirTable sync...', 'info');
        
        try {
            // Show confirmation dialog
            if (!confirm('This will sync all JSON files in the json_files directory to AirTable. Only records for usernames that already exist in your AirTable will be updated. Continue?')) {
                console.log('🔄 AirTable sync cancelled by user');
                
                if (syncStatus) {
                    syncStatus.innerHTML = '<div class="alert alert-secondary"><i class="fas fa-ban me-2"></i>Sync operation cancelled.</div>';
                }
                
                return;
            }
            
            // Call backend API to sync AirTable data
            const response = await fetch('/api/sync_airtable', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    username: this.currentUser.username,
                    timestamp: new Date().toISOString()
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                console.log('✅ AirTable sync completed successfully:', result);
                
                if (syncStatus) {
                    syncStatus.innerHTML = `<div class="alert alert-success"><i class="fas fa-check-circle me-2"></i>Sync completed! Updated ${result.updated_count} records.</div>`;
                }
                
                this.showToast(`Sync completed! Updated ${result.updated_count} records.`, 'success', 8000);
            } else {
                console.error('❌ AirTable sync failed:', result.error);
                
                if (syncStatus) {
                    syncStatus.innerHTML = `<div class="alert alert-danger"><i class="fas fa-exclamation-circle me-2"></i>Sync failed: ${result.error}</div>`;
                }
                
                this.showToast(`Sync failed: ${result.error}`, 'danger', 8000);
            }
        } catch (error) {
            console.error('❌ Error during AirTable sync:', error);
            
            if (syncStatus) {
                syncStatus.innerHTML = `<div class="alert alert-danger"><i class="fas fa-exclamation-triangle me-2"></i>Sync error: ${error.message}</div>`;
            }
            
            this.showToast(`Sync error: ${error.message}`, 'danger', 8000);
        }
    }

    // Chat System Methods
    initChat() {
        console.log('💬 Initializing chat system...');
        this.chatOpen = false;
        this.unreadCount = 0;
        this.messages = [];
        this.setupChatListeners();
        // Load stored messages first, then sync with Supabase
        this.loadStoredChatHistory();
        this.loadChatHistory();
        this.checkQuickActionsPreference();
    }
    
    checkQuickActionsPreference() {
        // Check if user has previously hidden quick actions
        const isHidden = localStorage.getItem('chat_quick_actions_hidden');
        if (isHidden === 'true') {
            const quickActions = document.getElementById('chat-quick-actions');
            if (quickActions) {
                quickActions.classList.add('hidden');
            }
        }
    }

    setupChatListeners() {
        // Listen for new messages from admin
        if (this.socket) {
            // Join user-specific room for targeted messages
            console.log('🔔 [FRONTEND] Attempting to join room for user:', this.currentUser.username);
            this.socket.emit('join_user_room', {
                username: this.currentUser.username
            });
            console.log('🔔 [FRONTEND] Join room request sent');
            
            // Listen for admin replies
            this.socket.on('admin_reply', (data) => {
                console.log('💬 Admin reply received:', data);
                this.hideTypingIndicator();
                this.addMessage({
                    text: data.message,
                    timestamp: data.timestamp,
                    isAdmin: true,
                    adminName: data.admin_name || 'Support'
                }, false);
                this.updateUnreadCount();
                this.showNotification(`New message from ${data.admin_name || 'Support'}`);
            });

            this.socket.on('admin_typing', (data) => {
                this.showTypingIndicator();
            });

            this.socket.on('admin_stopped_typing', (data) => {
                this.hideTypingIndicator();
            });
            
            // ULTRA-FIX: Comprehensive Real-Time Event Handlers
            
            // Handle test messages (for debugging)
            this.socket.on('test_message', (data) => {
                console.log('🧪 [REALTIME] Test message received:', data);
                this.showToast(`Test: ${data.message}`, 'success', 3000);
            });
            
            // Handle comprehensive message deletion (NEW ENHANCED EVENT)
            this.socket.on('chat_messages_deleted', (data) => {
                console.log('🔥 [REALTIME] Chat messages deleted event received:', data);
                console.log('🔥 [REALTIME] Event for user:', data.username, 'Current user:', this.currentUser?.username);
                
                // Only process if this event is for current user
                if (data.username === this.currentUser?.username) {
                    console.log('🔥 [REALTIME] Processing deletion for current user');
                    
                    // FORCE complete chat reload from Supabase
                    this.forceReloadChat('Messages deleted by support');
                    
                    // Show notification
                    this.showToast('Your conversation history has been cleared by support.', 'warning', 5000);
                } else {
                    console.log('🔥 [REALTIME] Deletion event not for current user, ignoring');
                }
            });
            
            // Handle force chat refresh (broadcasts to ALL users)
            this.socket.on('force_chat_refresh', (data) => {
                console.log('🔥 [REALTIME] Force chat refresh received:', data);
                
                // If this affects current user, force reload
                if (data.affected_user === this.currentUser?.username) {
                    console.log('🔥 [REALTIME] Force refresh affects current user - reloading');
                    this.forceReloadChat(`Chat updated: ${data.action}`);
                }
            });
            
            // Legacy handler (keep for backward compatibility)
            this.socket.on('messages_deleted', (data) => {
                console.log('🔔 [LEGACY] Old messages_deleted event received:', data);
                this.forceReloadChat('Messages cleared by admin');
                this.showToast('Your conversation history has been cleared by support.', 'info', 5000);
            });
            
            // Handle connection events
            this.socket.on('disconnect', () => {
                console.log('💬 Chat disconnected');
            });
            
            this.socket.on('reconnect', () => {
                console.log('💬 Chat reconnected');
                // Rejoin room on reconnect
                console.log('🔔 [FRONTEND] Rejoining room after reconnect for user:', this.currentUser.username);
                this.socket.emit('join_user_room', {
                    username: this.currentUser.username
                });
                console.log('🔔 [FRONTEND] Rejoin room request sent');
            });
        }
    }

    async loadChatHistory() {
        // Load previous messages for this user from Supabase
        if (this.currentUser) {
            console.log('💬 Loading chat history for:', this.currentUser.username);
            
            try {
                console.log('💬 Making request to /api/user/chat/history/', this.currentUser.username);
                const response = await fetch(`/api/user/chat/history/${this.currentUser.username}`);
                console.log('💬 Chat history response status:', response.status);
                const data = await response.json();
                console.log('💬 Chat history response data:', data);
                
                if (data.success && data.messages) {
                    console.log('💬 Processing', data.messages.length, 'messages from Supabase');
                    // Convert Supabase messages to chat format
                    this.messages = data.messages.map(msg => ({
                        id: parseTimestamp(msg.created_at || msg.timestamp),
                        text: msg.message,
                        timestamp: parseTimestamp(msg.created_at || msg.timestamp),
                        isAdmin: msg.is_admin || false,
                        category: msg.category || 'general',
                        adminName: msg.admin_name || 'Support',
                        read: true
                    }));
                    
                    console.log('💬 Loaded', this.messages.length, 'messages from Supabase');
                } else {
                    console.log('💬 No previous messages found or error occurred, showing welcome message');
                    console.log('💬 Response success:', data.success, 'Messages:', data.messages);
                    // Show welcome message if no history
                    const welcomeMessage = {
                        id: Date.now(),
                        text: '👋 Welcome to Fan Finder! I\'m here to help you with any questions about the app, payments, or technical support.',
                        timestamp: new Date().toISOString(),
                        isAdmin: true,
                        adminName: 'Support Bot',
                        read: true
                    };
                    this.messages.push(welcomeMessage);
                }
                
                console.log('💬 Rendering', this.messages.length, 'messages');
                this.renderMessages();
                
            } catch (error) {
                console.error('❌ Error loading chat history:', error);
                // Fallback to welcome message
                const welcomeMessage = {
                    id: Date.now(),
                    text: '👋 Welcome to Fan Finder! I\'m here to help you with any questions about the app, payments, or technical support.',
                    timestamp: new Date().toISOString(),
                    isAdmin: true,
                    adminName: 'Support Bot', 
                    read: true
                };
                this.messages.push(welcomeMessage);
                this.renderMessages();
            }
        } else {
            console.log('💬 No current user, cannot load chat history');
        }
    }

    addMessage(messageData, isUser = true) {
        const message = {
            id: messageData.id || Date.now(),
            text: messageData.text,
            timestamp: parseTimestamp(messageData.timestamp) || new Date().toISOString(),
            isAdmin: !isUser,
            read: isUser // User messages are always read, admin messages start unread
        };

        this.messages.push(message);
        this.renderMessages();
        this.scrollToBottom();

        // Save to localStorage for persistence
        this.saveChatHistory();

        // If chat is closed and it's an admin message, show notification
        if (!this.chatOpen && !isUser) {
            this.updateUnreadCount();
        }
        
        console.log('Message added:', message);
    }

    renderMessages() {
        const messagesContainer = document.getElementById('chat-messages');
        if (!messagesContainer) return;

        // Clear existing messages (keep welcome structure)
        const messageDay = messagesContainer.querySelector('.message-day');
        messagesContainer.innerHTML = '';
        if (messageDay) {
            messagesContainer.appendChild(messageDay);
        }

        this.messages.forEach(message => {
            const messageEl = document.createElement('div');
            messageEl.className = `message ${message.isAdmin ? 'admin-message' : 'user-message'}`;
            
            const timestamp = message.timestamp || message.created_at;
            let time = 'Invalid time';
            
            if (timestamp) {
                try {
                    // Use our utility function to parse the timestamp
                    const parsedTimestamp = parseTimestamp(timestamp);
                    const date = new Date(parsedTimestamp);
                    if (date instanceof Date && !isNaN(date)) {
                        time = date.toLocaleTimeString([], {
                            hour: '2-digit',
                            minute: '2-digit'
                        });
                    }
                } catch (e) {
                    console.error('Error parsing timestamp:', timestamp, e);
                    time = 'Invalid time';
                }
            }

            messageEl.innerHTML = `
                <div class="message-avatar">
                    <i class="fas fa-${message.isAdmin ? 'robot' : 'user'}"></i>
                </div>
                <div class="message-content">
                    <div class="message-bubble">
                        <div class="message-text">${this.escapeHtml(message.text)}</div>
                        <div class="message-time">${time}</div>
                    </div>
                </div>
            `;

            messagesContainer.appendChild(messageEl);
        });
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    updateUnreadCount() {
        const unreadMessages = this.messages.filter(msg => msg.isAdmin && !msg.read);
        this.unreadCount = unreadMessages.length;

        const badge = document.getElementById('chat-badge');
        const count = document.getElementById('chat-badge-count');

        if (this.unreadCount > 0) {
            badge.style.display = 'flex';
            count.textContent = this.unreadCount > 9 ? '9+' : this.unreadCount;
        } else {
            badge.style.display = 'none';
        }
    }

    markMessagesAsRead() {
        this.messages.forEach(msg => {
            if (msg.isAdmin && !msg.read) {
                msg.read = true;
            }
        });
        this.updateUnreadCount();
        this.saveChatHistory();
    }

    scrollToBottom() {
        setTimeout(() => {
            const messagesContainer = document.getElementById('chat-messages');
            if (messagesContainer) {
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }
        }, 100);
    }

    showTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) {
            indicator.style.display = 'flex';
            this.scrollToBottom();
        }
    }

    hideTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) {
            indicator.style.display = 'none';
        }
    }

    saveChatHistory() {
        if (this.currentUser) {
            localStorage.setItem(`chat_history_${this.currentUser.username}`, JSON.stringify(this.messages));
        }
    }

    loadStoredChatHistory() {
        if (this.currentUser) {
            const stored = localStorage.getItem(`chat_history_${this.currentUser.username}`);
            if (stored) {
                try {
                    this.messages = JSON.parse(stored);
                    this.renderMessages();
                    this.updateUnreadCount();
                } catch (e) {
                    console.error('💬 Error loading chat history:', e);
                }
            }
        }
    }

    showNotification(message) {
        // Show browser notification if permission granted
        if (Notification.permission === 'granted') {
            new Notification('Fan Finder Support', {
                body: message,
                icon: '/letter-f.ico'
            });
        }
    }

    // ULTRA-FIX: Force reload chat from Supabase (real-time sync)
    async forceReloadChat(reason = 'Chat updated') {
        console.log('🔥 [REALTIME] Force reloading chat from Supabase -', reason);
        
        try {
            // Clear ALL local data
            this.messages = [];
            
            // Clear localStorage completely for this user
            if (this.currentUser) {
                const cacheKey = `chat_history_${this.currentUser.username}`;
                localStorage.removeItem(cacheKey);
                console.log('🔥 [REALTIME] Cleared localStorage cache:', cacheKey);
            }
            
            // Clear the chat display immediately
            this.renderMessages();
            
            // Force reload from Supabase (bypass cache)
            console.log('🔥 [REALTIME] Reloading messages from Supabase...');
            await this.loadChatHistory();
            
            console.log('🔥 [REALTIME] Chat force reload completed successfully');
            
            // Show subtle notification
            if (reason) {
                console.log('🔥 [REALTIME] Chat refreshed:', reason);
            }
            
        } catch (error) {
            console.error('🔥 [REALTIME] Error during force reload:', error);
            // Fallback: at least clear the display
            this.messages = [];
            this.renderMessages();
        }
    }
}

// Global Chat Functions
function toggleChat() {
    const chatWindow = document.getElementById('chat-window');
    const app = window.app;
    
    if (chatWindow.classList.contains('open')) {
        chatWindow.classList.remove('open');
        app.chatOpen = false;
    } else {
        chatWindow.classList.add('open');
        app.chatOpen = true;
        app.markMessagesAsRead();
        app.scrollToBottom();
        
        // Focus input
        setTimeout(() => {
            const input = document.getElementById('chat-input');
            if (input) input.focus();
        }, 300);
    }
}

function detectMessageCategory(message) {
    const text = message.toLowerCase();
    
    if (text.includes('payment') || text.includes('paid') || text.includes('subscription') || text.includes('billing')) {
        return 'payment';
    }
    if (text.includes('error') || text.includes('bug') || text.includes('not working') || text.includes('problem') || text.includes('issue')) {
        return 'technical';
    }
    if (text.includes('activate') || text.includes('activation') || text.includes('account')) {
        return 'activation';
    }
    if (text.includes('help') || text.includes('how') || text.includes('question')) {
        return 'help';
    }
    
    return 'general';
}

function sendMessage() {
    const input = document.getElementById('chat-input');
    const app = window.app;
    
    if (!input || !app) {
        console.log('sendMessage: Input or app not found');
        return;
    }
    
    const text = input.value.trim();
    if (!text) {
        console.log('sendMessage: Empty message, ignoring');
        return;
    }

    console.log('sendMessage: Processing message:', text);

    // Determine category based on message content
    const category = detectMessageCategory(text);
    console.log('sendMessage: Detected category:', category);

    // Add user message
    const messageData = { 
        text, 
        category: category,
        timestamp: new Date().toISOString()
    };
    console.log('sendMessage: Adding message to UI:', messageData);
    app.addMessage(messageData, true);
    
    // Clear input
    input.value = '';

    // Send to server (via Socket.IO)
    if (app.socket && app.currentUser) {
        const payload = {
            username: app.currentUser.username,
            message: text,
            category: category,
            user_id: app.currentUser.username,
            timestamp: new Date().toISOString()
        };
        console.log('sendMessage: Sending to server via Socket.IO:', payload);
        app.socket.emit('user_message', payload);
        console.log('sendMessage: Message sent to server');
    } else {
        console.log('sendMessage: Socket or user not available:', {socket: !!app.socket, user: !!app.currentUser});
    }
    
    // Save chat history after sending message
    console.log('sendMessage: Saving chat history');
    app.saveChatHistory();
    console.log('sendMessage: Process completed');
}

function sendQuickMessage(text) {
    const input = document.getElementById('chat-input');
    if (input) {
        input.value = text;
        sendMessage();
    }
}

function hideQuickActions() {
    const quickActions = document.getElementById('chat-quick-actions');
    if (quickActions) {
        quickActions.classList.add('hidden');
        // Save user preference to hide quick actions
        localStorage.setItem('chat_quick_actions_hidden', 'true');
    }
}

function handleChatKeypress(event) {
    if (event.key === 'Enter') {
        event.preventDefault();
        sendMessage();
    }
}

// Global functions for HTML onclick events
function clearUsers(scriptType) {
    if (window.app) {
        window.app.clearCollectedUsers(scriptType);
        window.app.showToast(`${scriptType.toUpperCase()} users cleared`, 'info', 2000);
    }
}

function testUsers() {
    if (window.app) {
        console.log('Testing user collection...');
        
        // Simulate some user collection messages
        const testMessages = [
            'New user found: testuser123',
            'Collected user: example_user',
            'User collected: demo_account',
            'Found user: sample_profile',
            'Adding user: another_test'
        ];
        
        testMessages.forEach((message, index) => {
            setTimeout(() => {
                const scriptType = index % 2 === 0 ? 'discovery' : 'keyword';
                const timestamp = new Date().toLocaleTimeString();
                
                // Check for new users without logging
                window.app.checkForNewUser(scriptType, message, timestamp);
            }, index * 500);
        });
        
        window.app.showToast('Test users being added! Check the users sections.', 'info', 3000);
    }
}

function copyPaymentDetails() {
    if (window.app && window.app.paymentDetails) {
        navigator.clipboard.writeText(window.app.paymentDetails).then(() => {
            window.app.showToast('Payment details copied to clipboard!', 'success', 3000);
        }).catch(() => {
            window.app.showToast('Failed to copy payment details', 'danger');
        });
    }
}

function submitPaymentProof() {
    const screenshotInput = document.getElementById('payment-screenshot');
    const noteInput = document.getElementById('payment-note');
    
    const screenshotFile = screenshotInput.files[0];
    const note = noteInput.value.trim();
    
    // Validate inputs
    if (!screenshotFile && !note) {
        window.app.showToast('Please upload a screenshot or add a note', 'warning');
        return;
    }
    
    // Get current user info if available
    let username = '';
    try {
        const user = sessionStorage.getItem('fanfinder_user');
        if (user) {
            const userData = JSON.parse(user);
            username = userData.username || '';
        }
    } catch (e) {
        console.log('Could not get username from sessionStorage');
    }
    
    // Prepare form data
    const formData = new FormData();
    if (screenshotFile) {
        formData.append('screenshot', screenshotFile);
    }
    formData.append('note', note);
    formData.append('username', username);
    formData.append('timestamp', new Date().toISOString());
    
    // Send to backend
    fetch('/api/submit_payment_proof', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            window.app.showToast('Payment proof submitted successfully!', 'success');
            // Clear the form
            screenshotInput.value = '';
            noteInput.value = '';
        } else {
            window.app.showToast(data.message || 'Failed to submit payment proof', 'danger');
        }
    })
    .catch(error => {
        console.error('Error submitting payment proof:', error);
        window.app.showToast('Error submitting payment proof', 'danger');
    });
}

// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    console.log('🌐 DOM loaded, initializing app...');
    window.app = new UserFinderApp();
    
    // Auto-Update System
    let updateCheckTimeout;
    
    function checkForUpdates() {
        console.log('[UPDATE] Checking for updates...');
        
        fetch('/api/check_updates')
            .then(response => response.json())
            .then(data => {
                console.log('[UPDATE] Update check result:', data);
                
                if (data.update_available) {
                    showUpdateBanner(data);
                } else {
                    console.log(`[UPDATE] No updates available. Current version: ${data.current_version}`);
                }
            })
            .catch(error => {
                console.log('[UPDATE] Update check failed:', error);
            });
    }
    
    function showUpdateBanner(updateInfo) {
        console.log('[UPDATE] Showing update banner for version:', updateInfo.latest_version);
        
        const currentVersionText = document.getElementById('current-version');
        const versionText = document.getElementById('update-version');
        const notesDiv = document.getElementById('update-notes');
        const descriptionDiv = document.getElementById('update-description');
        
        currentVersionText.textContent = `v${updateInfo.current_version}`;
        versionText.textContent = `v${updateInfo.latest_version}`;
        
        // Show release notes if available
        if (updateInfo.release_notes && updateInfo.release_notes.trim()) {
            notesDiv.innerHTML = updateInfo.release_notes
                .replace(/\n/g, '<br>')
                .substring(0, 300) + (updateInfo.release_notes.length > 300 ? '...' : '');
            descriptionDiv.style.display = 'block';
        } else {
            descriptionDiv.style.display = 'none';
        }
        
        // Store update info for download
        window.updateInfo = updateInfo;
        
        // Show modal (required - cannot be dismissed)
        const updateModal = new bootstrap.Modal(document.getElementById('updateRequiredModal'), {
            backdrop: 'static',
            keyboard: false
        });
        updateModal.show();
    }
    
    function downloadUpdate() {
        if (!window.updateInfo || !window.updateInfo.download_url) {
            console.log('[UPDATE] No download URL available');
            window.app.showToast('Download URL not available. Please check manually.', 'warning');
            return;
        }
        
        console.log('[UPDATE] Starting automatic update download and installation...');
        
        // Show progress modal immediately
        showUpdateProgressModal();
        
        // Start the automatic update process
        fetch('/api/download_update', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                console.log('[UPDATE] Update completed successfully:', data);
                showUpdateSuccessModal(data);
            } else {
                console.log('[UPDATE] Update failed:', data.error);
                showUpdateErrorModal(data.error);
            }
        })
        .catch(error => {
            console.log('[UPDATE] Update request failed:', error);
            showUpdateErrorModal('Network error during update: ' + error.message);
        });
    }
    
    function showUpdateProgressModal() {
        const modal = document.createElement('div');
        modal.innerHTML = `
            <div class="modal fade" id="updateProgressModal" tabindex="-1" data-bs-backdrop="static">
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">
                                <i class="fas fa-download me-2"></i>Installing Update...
                            </h5>
                        </div>
                        <div class="modal-body text-center">
                            <div class="spinner-border text-primary mb-3" role="status">
                                <span class="visually-hidden">Loading...</span>
                            </div>
                            <h6>🔄 Updating User Finder to v${window.updateInfo.latest_version}</h6>
                            <p class="text-muted mb-3">Please wait while we download and install the update...</p>
                            
                            <div class="progress mb-3">
                                <div class="progress-bar progress-bar-striped progress-bar-animated" 
                                     role="progressbar" style="width: 100%"></div>
                            </div>
                            
                            <small class="text-muted">
                                • Downloading update package<br>
                                • Extracting and replacing files<br>
                                • Updating configuration<br>
                            </small>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        window.updateModal = new bootstrap.Modal(modal.querySelector('.modal'));
        window.updateModal.show();
        
        // Store modal element for cleanup
        window.updateModalElement = modal;
    }
    
    function showUpdateSuccessModal(data) {
        // Close progress modal
        if (window.updateModal) {
            window.updateModal.hide();
        }
        
        // Close the update required modal
        const updateRequiredModal = bootstrap.Modal.getInstance(document.getElementById('updateRequiredModal'));
        if (updateRequiredModal) {
            updateRequiredModal.hide();
        }
        
        setTimeout(() => {
            const modal = document.createElement('div');
            modal.innerHTML = `
                <div class="modal fade" id="updateSuccessModal" tabindex="-1">
                    <div class="modal-dialog modal-dialog-centered">
                        <div class="modal-content">
                            <div class="modal-header text-white border-0" style="background: #FF6B35;">
                                <h5 class="modal-title">
                                    <i class="fas fa-check-circle me-2"></i>Update Completed!
                                </h5>
                                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body p-3">
                                <div class="text-center mb-3">
                                    <div class="rounded-circle mx-auto mb-2" style="width: 50px; height: 50px; display: flex; align-items: center; justify-content: center; background: #FF6B35;">
                                        <i class="fas fa-check text-white" style="font-size: 20px;"></i>
                                    </div>
                                    <h6 class="mb-1">Installation Complete!</h6>
                                    <small class="text-muted">Successfully updated to v${data.new_version}</small>
                                </div>
                                
                                <div class="row text-center mb-3">
                                    <div class="col-5">
                                        <div class="bg-light rounded p-2">
                                            <small class="text-muted">Previous</small>
                                            <div class="fw-bold text-muted small">${window.updateInfo.current_version}</div>
                                        </div>
                                    </div>
                                    <div class="col-2 d-flex align-items-center justify-content-center">
                                        <i class="fas fa-arrow-right" style="color: #FF6B35;"></i>
                                    </div>
                                    <div class="col-5">
                                        <div class="rounded p-2 text-white" style="background: #FF6B35;">
                                            <small>Current</small>
                                            <div class="fw-bold small">${data.new_version}</div>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="alert alert-info border-0 py-2" style="background: rgba(255, 107, 53, 0.1); border-radius: 6px;">
                                    <div class="d-flex align-items-center">
                                        <i class="fas fa-power-off me-2" style="color: #FF6B35;"></i>
                                        <div>
                                            <strong style="color: #FF6B35;" class="small">Restart Required</strong><br>
                                            <small class="text-muted">Complete the update by restarting the application</small>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div class="modal-footer border-0 p-3 pt-0">
                                <button type="button" class="btn w-100 fw-bold" onclick="restartApplication()" style="background: linear-gradient(135deg, #FF6B35 0%, #F7931E 100%); color: white; border: none; border-radius: 6px; padding: 8px 16px;">
                                    <i class="fas fa-power-off me-2"></i>Restart Now
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            document.body.appendChild(modal);
            const modalInstance = new bootstrap.Modal(modal.querySelector('.modal'));
            modalInstance.show();
            
            // Update modal is already closed
            
            // Clean up modal after closing
            modal.addEventListener('hidden.bs.modal', () => {
                document.body.removeChild(modal);
            });
            
        }, 500);
        
        // Clean up progress modal
        if (window.updateModalElement) {
            document.body.removeChild(window.updateModalElement);
        }
    }
    
    function showUpdateErrorModal(error) {
        // Close progress modal
        if (window.updateModal) {
            window.updateModal.hide();
        }
        
        setTimeout(() => {
            const modal = document.createElement('div');
            modal.innerHTML = `
                <div class="modal fade" id="updateErrorModal" tabindex="-1">
                    <div class="modal-dialog modal-dialog-centered">
                        <div class="modal-content">
                            <div class="modal-header bg-danger text-white">
                                <h5 class="modal-title">
                                    <i class="fas fa-exclamation-triangle me-2"></i>Update Failed
                                </h5>
                                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body">
                                <div class="alert alert-danger">
                                    <i class="fas fa-times-circle me-2"></i>
                                    <strong>Automatic update failed</strong>
                                </div>
                                
                                <p><strong>Error Details:</strong></p>
                                <div class="bg-light p-2 rounded">
                                    <code>${error}</code>
                                </div>
                                
                                <hr>
                                
                                <p><strong>📝 Manual Update Instructions:</strong></p>
                                <ol>
                                    <li>Download update manually from GitHub</li>
                                    <li>Extract ZIP file to User Finder folder</li>
                                    <li>Replace existing files</li>
                                    <li>Restart User Finder</li>
                                </ol>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-primary" onclick="window.open(window.updateInfo.download_url, '_blank')">
                                    <i class="fas fa-external-link-alt me-2"></i>Download Manually
                                </button>
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                    Close
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            document.body.appendChild(modal);
            const modalInstance = new bootstrap.Modal(modal.querySelector('.modal'));
            modalInstance.show();
            
            // Clean up modal after closing
            modal.addEventListener('hidden.bs.modal', () => {
                document.body.removeChild(modal);
            });
            
        }, 500);
        
        // Clean up progress modal
        if (window.updateModalElement) {
            document.body.removeChild(window.updateModalElement);
        }
    }
    
    function restartApplication() {
        window.app.showToast('Restarting User Finder...', 'info');
        
        // Send restart command to backend
        fetch('/api/restart_application', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => {
            if (response.ok) {
                // Backend is restarting, show loading and wait for reconnection
                showRestartProgress();
            } else {
                throw new Error('Restart request failed');
            }
        })
        .catch(error => {
            console.log('[RESTART] Backend restart failed, doing page reload:', error);
            // Fallback to page reload if backend restart fails
            setTimeout(() => {
                window.location.reload();
            }, 1000);
        });
    }
    
    function showRestartProgress() {
        // Close update success modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('updateSuccessModal'));
        if (modal) modal.hide();
        
        // Show restart progress modal
        const restartModal = document.createElement('div');
        restartModal.innerHTML = `
            <div class="modal fade" id="restartProgressModal" tabindex="-1" data-bs-backdrop="static" data-bs-keyboard="false">
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content">
                        <div class="modal-body text-center p-5">
                            <div class="spinner-border text-primary mb-3" role="status" style="width: 3rem; height: 3rem;">
                                <span class="visually-hidden">Loading...</span>
                            </div>
                            <h5 class="mb-2">Restarting User Finder...</h5>
                            <p class="text-muted mb-0">Please wait while the application restarts with the new updates.</p>
                            <div class="mt-3">
                                <small class="text-muted">
                                    <i class="fas fa-circle-notch fa-spin me-1"></i>
                                    This may take up to 10 seconds
                                </small>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(restartModal);
        const restartBootstrapModal = new bootstrap.Modal(restartModal.querySelector('#restartProgressModal'));
        restartBootstrapModal.show();
        
        // Try to reconnect after restart
        setTimeout(() => {
            checkApplicationRestart();
        }, 3000);
    }
    
    function checkApplicationRestart() {
        let attempts = 0;
        const maxAttempts = 20; // Try for up to 20 seconds
        
        const checkConnection = () => {
            attempts++;
            fetch('/api/script_status', { method: 'GET' })
                .then(response => {
                    if (response.ok) {
                        // Application is back online
                        window.location.reload();
                    } else {
                        throw new Error('Not ready yet');
                    }
                })
                .catch(error => {
                    if (attempts < maxAttempts) {
                        setTimeout(checkConnection, 1000);
                    } else {
                        // Max attempts reached, just reload
                        window.location.reload();
                    }
                });
        };
        
        checkConnection();
    }
    
    // Update is now required - no dismiss function needed
    
    // Make functions global so HTML can access them
    window.downloadUpdate = downloadUpdate;
    window.restartApplication = restartApplication;
    
    // Payment proof submission function
    window.submitPaymentProof = function() {
        const form = document.getElementById('payment-proof-form');
        const formData = new FormData(form);
        
        // Get values for validation
        const screenshot = document.getElementById('payment-proof-screenshot').files[0];
        const note = document.getElementById('payment-proof-note').value.trim();
        
        // Validate required fields
        if (!screenshot) {
            window.app.showToast('Please select a screenshot to upload', 'warning');
            return;
        }
        
        // Show loading state
        const submitBtn = form.querySelector('button[type="button"]');
        const originalText = submitBtn.innerHTML;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Submitting...';
        submitBtn.disabled = true;
        
        // Send to backend
        fetch('/api/submit_payment_proof', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                window.app.showToast('Payment proof submitted successfully!', 'success');
                // Clear the form
                form.reset();
                // Close the modal
                const modal = bootstrap.Modal.getInstance(document.getElementById('subscriptionModal'));
                if (modal) {
                    modal.hide();
                }
            } else {
                window.app.showToast(data.message || 'Failed to submit payment proof', 'danger');
            }
        })
        .catch(error => {
            console.error('Error submitting payment proof:', error);
            window.app.showToast('Error submitting payment proof', 'danger');
        })
        .finally(() => {
            // Restore button state
            submitBtn.innerHTML = originalText;
            submitBtn.disabled = false;
        });
    };
    
    // Copy payment details function
    window.copyPaymentDetails = function() {
        if (window.app && window.app.paymentDetails) {
            navigator.clipboard.writeText(window.app.paymentDetails).then(() => {
                window.app.showToast('Payment details copied to clipboard!', 'success');
            }).catch(err => {
                console.error('Failed to copy: ', err);
                window.app.showToast('Failed to copy payment details', 'danger');
            });
        } else {
            window.app.showToast('Payment details not available', 'warning');
        }
    };
    
    // Check for updates 5 seconds after page loads
    setTimeout(() => {
        checkForUpdates();
        
        // Then check every 30 minutes
        setInterval(checkForUpdates, 30 * 60 * 1000);
    }, 5000);
});