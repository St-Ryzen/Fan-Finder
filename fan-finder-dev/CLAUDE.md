# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Fan Finder is a TikTok user discovery automation tool with a web-based interface. It features real-time progress tracking across multiple concurrent search instances using Socket.IO, session-based authentication, and Supabase backend integration.

## Architecture

### Backend (Flask + Socket.IO)

**Entry Point**: `app/backend/app.py`

The backend is a Flask application with Socket.IO for real-time bidirectional communication. Key architectural patterns:

- **Script Execution Model**: Discovery and Keyword search scripts run as subprocess instances with output streaming to the frontend via Socket.IO
- **Instance Management**: Each search can run multiple instances (e.g., Discovery Instance 1, 2, 3) with independent progress tracking
- **Output Parsing**: Python script output is parsed using regex patterns to extract user progress data
  - Discovery format: `[DISCOVERY] [SUCCESS] Collected user: username (X/Y - Z%)`
  - Keyword format: `[KEYWORD] [SUCCESS] New user found: username (X/Y - Z%)`
- **Socket.IO Events**: Server emits `script_progress` and `user_collected` events with instance_number for routing

**Key Modules**:
- `license_manager.py`: Supabase database connection and authentication
- `credential_manager.py`: Model account credential encryption/decryption
- `security_middleware.py`: Request security validation
- `config_protection.py`: Configuration file protection

### Frontend (Vanilla JS + Bootstrap)

**Main Files**:
- `app/frontend/index.html` - HTML structure with instance-based UI containers
- `app/frontend/app.js` - UserFinderApp class with Socket.IO client
- `app/frontend/style.css` - Glassmorphism design with 0.1-0.2 opacity backgrounds

**Architecture**:
- **UserFinderApp Class**: Main application controller with state management
- **Instance-Based UI**: Each search instance (discovery-1, discovery-2, keyword-1, etc.) has dedicated DOM elements:
  - `instance-{searchType}-{instanceNumber}` - Container
  - `progress-container-instance-{searchType}-{instanceNumber}` - Progress bar
  - `progress-bar-instance-{searchType}-{instanceNumber}` - Progress visual
- **Socket.IO Listeners**: Real-time event handlers for progress, user collection, and script output
- **Session Storage**: Authentication state persists only for current browser session

### Search Scripts

Located in `app/scripts/`:
- `discoverySearch.py` - Discovery-based user search with instance support
- `keywordSearch.py` - Keyword-based user search with instance support

These output progress in the formats mentioned above, which are parsed by the backend.

## Critical Code Patterns

### Progress Tracking Flow

1. Python script outputs: `[DISCOVERY] [SUCCESS] Collected user: username (1/100 - 1.0%)`
2. Backend regex (app.py:399) extracts: username, collected_count, target_count, progress%
3. Backend emits Socket.IO event with instance_number:
   ```javascript
   socketio.emit('script_progress', {
     script_type: 'discovery',
     instance_number: 1,
     collected_users: 1,
     target_users: 100,
     progress: 1
   })
   ```
4. Frontend receives and routes to `updateInstanceProgress(scriptType, progress, collected, target, instanceNumber)`
5. DOM element `progress-bar-instance-discovery-1` updates with progress

### Important: Regex Pattern Matching

The regex pattern at app.py:399 must match BOTH discovery and keyword formats:
```python
progress_match = re.search(r'(?:collected user|new user found):\s*([^\s]+)\s*\((\d+)/(\d+)\s*-\s*([\d.]+)%\)', clean_line, re.IGNORECASE)
```

When modifying Python scripts' output format, this regex must be updated accordingly. Groups captured:
- Group 1: username
- Group 2: collected count
- Group 3: target count
- Group 4: progress percentage

## Startup & Development

### Windows Startup
```bash
server-for-windows.bat
```

This script:
1. Auto-detects available port (5000-5999)
2. Checks Python installation
3. Installs dependencies via pip
4. Starts Flask server on detected port
5. Opens Chrome automatically

### Starting Backend Only
```bash
cd app/backend
python app.py --port 5000
```

### Environment Variables

Create `.env` file with:
```
SUPABASE_URL=https://your-supabase-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-key
FLASK_PORT=5000
```

Or use `app/backend/config/secrets.json` for default credentials.

## Browser Developer Tools

When debugging progress updates, check:
- **Console**: Look for Socket.IO event logs like `[SCRIPT_PROGRESS] Received:`
- **Network**: Monitor WebSocket connections on the Socket.IO namespace
- **Elements**: Verify instance progress bar IDs exist: `progress-bar-instance-{type}-{number}`

Key console events to watch:
- `📊 [SCRIPT_PROGRESS] Received:` - Backend sent progress
- `📈 Progress elements not found for {scriptType}` - Instance UI not found (debug level, not an error)
- `[{TYPE.UPPERCASE()}] Updating Progress Bar:` - Progress being applied

## Common Tasks

### Modifying Search Output Format

If changing how Python scripts output progress:
1. Update the output format in discovery/keyword script
2. Update regex pattern in app.py:399 to match new format
3. Test with both discovery and keyword searches
4. Verify instance_number is being captured correctly

### Adding Instance Progress Display

New progress bar UI elements must follow naming convention:
```html
<div id="progress-container-instance-{type}-{number}">
  <div id="progress-bar-instance-{type}-{number}"></div>
  <div id="progress-text-instance-{type}-{number}"></div>
</div>
```

Frontend's `updateInstanceProgress()` in index.html:3026 will automatically route progress to these elements based on instance number.

### Debugging Socket.IO Events

Add logging in app.py for script output parsing (line 391-393):
```python
socketio.emit('script_output', {
    'script_type': self.script_type,
    'output': clean_line,
    'timestamp': datetime.now().strftime('%H:%M:%S')
})
```

Frontend receives via listener at app.js:334

## Database Schema

### Supabase Tables Required

**subscriptions** - User subscription info
- username, tier, created_at, expires_at

**models** - Model account management
- id (UUID), model_name, description, is_active, tags, created_at, updated_at

Migrations available in `app/backend/migrations/01_create_models_table.sql`

To initialize: Run `python app/backend/init_database.py` (provides SQL to paste in Supabase SQL editor)

## Performance Considerations

- **Socket.IO Buffering**: Progress events may batch under high load
- **Instance Limits**: Each instance spawns a Python subprocess; use reasonable instance counts
- **Frontend Updates**: Progress updates via DOM manipulation; don't create thousands of user list items
- **Regex Compilation**: Regex is compiled once per output line; optimize pattern if needed

## Version History Notable Changes

- **v1.1.1**: Fixed progress bar regex to match both discovery and keyword formats, added instance-specific routing
- **v1.0.9**: Multi-port support, unlimited premium tier, organized JSON file storage

## Deployment Notes

The application uses hardcoded Supabase credentials as fallback (app/backend/license_manager.py:48-51). For production distribution, ensure:
1. Environment variables are set for Supabase credentials
2. Database migrations are run on target system
3. Firebase/Supabase service keys are configured
4. Port 5000-5999 range is available on target machine
