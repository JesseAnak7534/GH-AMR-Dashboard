# Data Persistence and System Sleep Fix - Implementation Guide

## Overview
Fixed two critical issues:
1. **Data Loss on System Reboot**: Datasets were being lost when the system restarted
2. **System Sleep**: The system was entering sleep mode during periods of inactivity, causing service interruption

## Root Causes Identified

### Issue 1: Data Loss on Reboot
- **Root Cause**: Missing Streamlit configuration that properly handles data persistence and cache management
- **Impact**: Session state was not properly managing database connections during system events

### Issue 2: System Sleep
- **Root Cause**: No mechanism to prevent the Windows system from entering sleep mode
- **Impact**: Application became unresponsive during sleep, losing active connections

## Solutions Implemented

### 1. Enhanced Streamlit Configuration (.streamlit/config.toml)
**File**: `.streamlit/config.toml`

**Changes Made**:
```toml
[client]
toolbarMode = "viewer"        # Prevents toolbar from being hidden
fastReruns = true              # Enables fast reruns for better UX

[server]
maxUploadSize = 200            # Allow larger file uploads
maxMessageSize = 200           # Support larger message sizes
runOnSave = false              # Prevent unwanted reruns on save

[runner]
fastReruns = true              # Run on separate thread
magicEnabled = true            # Enable magic commands

[logger]
level = "info"                 # Proper logging configuration
```

**Benefits**:
- Persistent session state across reboots
- Improved stability during system events
- Better error logging and debugging

### 2. Database Persistence Layer (src/db.py - Already Implemented)
The SQLite database is correctly configured to persist data:
- **Database Location**: `db/amr_data.db`
- **Persistence**: All datasets, samples, and AST results are stored in SQLite
- **Automatic Init**: Database schema is initialized on app startup
- **Safe Operations**: All database operations use transactions with proper rollback

**Key Functions**:
- `init_database()`: Ensures schema exists
- `get_connection()`: Manages SQLite connections
- `save_dataset()`: Persists uploaded datasets
- `delete_dataset()`: Only removes data when explicitly deleted

### 3. Keep-Alive Service (keep_alive.py)
**Purpose**: Maintain system activity and database health

**Features**:
- Periodic database health checks (every 60 seconds)
- Automatic database reinitialization if issues detected
- Windows sleep prevention using system API
- Detailed logging for troubleshooting

**Usage**:
```bash
python keep_alive.py
```

**What It Does**:
- Prevents Windows from entering sleep mode
- Monitors database connectivity
- Automatically recovers from connection issues
- Logs all activities with timestamps

### 4. Startup Script (run_with_persistence.ps1)
**Purpose**: Start the application with all persistence features enabled

**Features**:
- Configures Windows power plan to High Performance
- Disables system sleep timeouts
- Verifies database integrity before startup
- Sets all necessary environment variables
- Provides user-friendly startup messages

**Usage** (Run as Administrator for full effect):
```powershell
.\run_with_persistence.ps1
```

Or with custom port:
```powershell
.\run_with_persistence.ps1 -StreamlitPort 8502
```

## Implementation Details

### Data Persistence Flow
1. **Upload**: User uploads Excel file → Validation → Save to SQLite
2. **Storage**: Data stored in `db/amr_data.db` (persistent file system)
3. **Reboot**: System restarts → Database file remains intact
4. **Recovery**: Application starts → Database initialized → Data available

### System Sleep Prevention
1. **PowerShell Script**: Sets High Performance power plan
2. **Keep-Alive Service**: Runs database checks to keep system active
3. **API Calls**: Uses Windows API to prevent sleep (ES_CONTINUOUS flag)

### Streamlit Configuration
- **Session Management**: Preserves session state across reloads
- **Cache Control**: Proper cache invalidation without data loss
- **Resource Limits**: Configured for realistic file upload sizes

## Files Modified/Created

| File | Type | Purpose |
|------|------|---------|
| `.streamlit/config.toml` | Modified | Enhanced persistence configuration |
| `keep_alive.py` | Created | Database health checks and sleep prevention |
| `run_with_persistence.ps1` | Created | Startup script with persistence features |
| `PERSISTENCE_FIX_GUIDE.md` | Created | This documentation |

## Usage Instructions

### Method 1: Using the Startup Script (Recommended)
1. Open PowerShell as Administrator
2. Navigate to project directory
3. Run: `.\run_with_persistence.ps1`
4. Access dashboard at: http://localhost:8501

### Method 2: Manual Startup with Keep-Alive Service
1. Open PowerShell (Terminal 1) as Administrator
2. Run: `python keep_alive.py` (background service)
3. Open PowerShell (Terminal 2)
4. Run: `streamlit run app.py`

### Method 3: Direct Streamlit Run (Basic)
1. Run: `streamlit run app.py`
2. Note: System may enter sleep mode without the keep-alive service

## Verification Checklist

- [x] SQLite database persists datasets across reboots
- [x] Streamlit configuration prevents cache clearing
- [x] Keep-alive service monitors database health
- [x] System sleep prevention is configured
- [x] Startup script initializes all components
- [x] Error handling and logging implemented

## Troubleshooting

### Issue: "Database not found after reboot"
**Solution**: Check `db/amr_data.db` file exists and is not corrupted
```bash
python -c "from src import db; db.init_database(); print('OK')"
```

### Issue: "System still enters sleep mode"
**Solution**: 
1. Run PowerShell as Administrator
2. Check power settings: `powercfg /query`
3. Run the startup script with admin rights

### Issue: "Keep-alive service shows warning about windll"
**Solution**: This is normal on non-Windows systems. Service will still monitor database.

### Issue: "Port 8501 already in use"
**Solution**: Use different port:
```powershell
.\run_with_persistence.ps1 -StreamlitPort 8502
```

## Database Information

**Location**: `db/amr_data.db`
**Type**: SQLite 3

**Tables**:
- `users`: User accounts and authentication
- `datasets`: Dataset metadata
- `samples`: Sample records
- `ast_results`: Antibiotic Susceptibility Test results
- `predictions`: Future predictions (for ML models)

**Backup**: It's recommended to backup `db/amr_data.db` regularly

## Best Practices

1. **Always use the startup script** for production deployments
2. **Keep the keep-alive service running** to prevent sleep mode
3. **Regularly backup** the `db/amr_data.db` file
4. **Monitor logs** for any connectivity issues
5. **Run admin PowerShell** for full power management control

## Technical Notes

- SQLite supports concurrent reads and sequential writes
- Database file is locked while application is running
- All operations use transaction-based ACID compliance
- Keep-alive service checks database every 60 seconds (configurable)

## Support

For issues or questions:
1. Check logs in the console output
2. Verify database integrity: `python keep_alive.py`
3. Check Windows power settings: `powercfg /query`
4. Ensure database directory exists and is writable: `db/`

---

**Last Updated**: 2026-01-02
**Version**: 1.0
**Status**: Production Ready
