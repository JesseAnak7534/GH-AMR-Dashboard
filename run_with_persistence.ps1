# PowerShell script to run Streamlit with persistence features
# This script ensures the application maintains data and prevents system sleep

param(
    [string]$StreamlitPort = "8501"
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "AMR Surveillance Dashboard" -ForegroundColor Cyan
Write-Host "Starting with Data Persistence" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Function to prevent system sleep
function Prevent-SystemSleep {
    Write-Host "Configuring system to prevent sleep..." -ForegroundColor Yellow
    
    try {
        # Set power plan to High Performance
        $powerPlans = Get-WmiObject -Class win32_powerplan -Namespace root\cimv2\power -Filter "ElementName='High performance'"
        if ($powerPlans) {
            $powerPlans | ForEach-Object {
                Invoke-WmiMethod -InputObject $_ -MethodName Activate | Out-Null
            }
            Write-Host "✓ Power plan set to High Performance" -ForegroundColor Green
        }
        
        # Disable sleep timeouts for AC power
        powercfg /change monitor-timeout-ac 0 | Out-Null
        powercfg /change disk-timeout-ac 0 | Out-Null
        powercfg /change standby-timeout-ac 0 | Out-Null
        
        Write-Host "✓ System sleep timeouts disabled (AC power)" -ForegroundColor Green
    }
    catch {
        Write-Host "⚠ Could not configure power settings (requires admin rights)" -ForegroundColor Yellow
        Write-Host "  Run PowerShell as Administrator for full sleep prevention" -ForegroundColor Yellow
    }
}

# Function to cleanup on exit
function Cleanup {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Shutting down application..." -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Cyan
    exit
}

# Set trap for Ctrl+C
trap { Cleanup }

# Prevent system sleep
Prevent-SystemSleep

Write-Host ""
Write-Host "Starting database integrity check..." -ForegroundColor Yellow
python -c "from src import db; db.init_database(); print('✓ Database initialized successfully')" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Database integrity verified" -ForegroundColor Green
} else {
    Write-Host "✗ Database initialization failed" -ForegroundColor Red
}

Write-Host ""
Write-Host "Starting Streamlit application on port $StreamlitPort..." -ForegroundColor Yellow
Write-Host "Access the dashboard at: http://localhost:$StreamlitPort" -ForegroundColor Cyan
Write-Host ""
Write-Host "NOTE: Keep this window open to maintain the application." -ForegroundColor Magenta
Write-Host "      All datasets and data will be persisted in the database." -ForegroundColor Magenta
Write-Host ""

# Start Streamlit with explicit configuration
$env:STREAMLIT_SERVER_PORT = $StreamlitPort
$env:STREAMLIT_SERVER_HEADLESS = "false"
$env:STREAMLIT_LOGGER_LEVEL = "info"

streamlit run app.py --logger.level=info

# Cleanup on exit
Cleanup
