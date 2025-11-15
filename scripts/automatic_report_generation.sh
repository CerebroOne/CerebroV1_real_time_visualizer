#!/bin/bash

###################################################################################
# Automatic Neural Compression Calibration Script
###################################################################################
# This script automates the full calibration workflow:
# 1. Launch TCP server on remote host (via SSH)
# 2. Start recording on neurocompressor
# 3. Send test pulse patterns
# 4. Stop recording
# 5. Download data and generate report
###################################################################################

set -e  # Exit on error

# ==================== Configuration ====================
DEFAULT_HOST="192.168.8.209"
DEFAULT_REMOTE_USER="miksolo"
REMOTE_BASE_PATH="/home/miksolo/git/CerebroV1/cerebro_embedded_esp32-s3_v1/scripts"
MQTT_CONTROL_TOPIC="esp32/control"
MQTT_GENERATOR_TOPIC="test/generator"

# ==================== Color Output ====================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ==================== Usage ====================
usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Automated neural compression calibration with report generation.

OPTIONS:
    -h, --host HOST          Remote host IP (default: $DEFAULT_HOST)
    -u, --user USER          Remote SSH user (default: $DEFAULT_USER)
    -o, --output DIR         Output directory for data and report (required)
    -n, --name NAME          Recording name/identifier (required)
    -p, --pulses PATTERN     Pulse pattern for test generator (default: "10 50 50 50")
    -d, --delay SECONDS      Delay after pulses before stopping (default: 5)
    -r, --remote-only        Only launch remote server (for manual testing)
    --help                   Show this help message

EXAMPLES:
    # Basic usage with required parameters
    $(basename "$0") -o ./calibration_data -n test_001 -p "10 50 50 50"

    # Custom host and longer recording
    $(basename "$0") -h 192.168.8.100 -o ./data -n exp_042 -p "20 30 40 50" -d 10

    # Remote server only (manual control)
    $(basename "$0") -h 192.168.8.209 -n manual_test -r

MQTT TOPICS:
    Control:   $MQTT_CONTROL_TOPIC (record_on/record_off)
    Generator: $MQTT_GENERATOR_TOPIC (pulse patterns)

EOF
    exit 1
}

# ==================== Parse Arguments ====================
HOST="$DEFAULT_HOST"
REMOTE_USER="$DEFAULT_REMOTE_USER"
OUTPUT_DIR=""
RECORDING_NAME=""
PULSE_PATTERN="10 50 50 50"
DELAY_AFTER_PULSES=5
REMOTE_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--host)
            HOST="$2"
            shift 2
            ;;
        -u|--user)
            REMOTE_USER="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -n|--name)
            RECORDING_NAME="$2"
            shift 2
            ;;
        -p|--pulses)
            PULSE_PATTERN="$2"
            shift 2
            ;;
        -d|--delay)
            DELAY_AFTER_PULSES="$2"
            shift 2
            ;;
        -r|--remote-only)
            REMOTE_ONLY=true
            shift
            ;;
        --help)
            usage
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            ;;
    esac
done

# ==================== Validate Arguments ====================
if [ -z "$RECORDING_NAME" ]; then
    log_error "Recording name is required (-n/--name)"
    usage
fi

if [ "$REMOTE_ONLY" = false ] && [ -z "$OUTPUT_DIR" ]; then
    log_error "Output directory is required (-o/--output) unless using --remote-only"
    usage
fi

# ==================== Setup ====================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RECORDING_FILE="${RECORDING_NAME}.json"
REMOTE_DATA_PATH="${REMOTE_BASE_PATH}/neural_data/${RECORDING_FILE}"

if [ "$REMOTE_ONLY" = false ]; then
    # Create output directory
    mkdir -p "$OUTPUT_DIR"
    OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"  # Get absolute path
    LOCAL_DATA_PATH="${OUTPUT_DIR}/${RECORDING_FILE}"
    LOCAL_REPORT_PATH="${OUTPUT_DIR}/${RECORDING_NAME}_report.pdf"
    
    log_info "Output directory: $OUTPUT_DIR"
    log_info "Local data path: $LOCAL_DATA_PATH"
    log_info "Local report path: $LOCAL_REPORT_PATH"
fi

# Global variable to track SSH PID
SSH_PID=""

# ==================== Cleanup Function ====================
cleanup() {
    local exit_code=$?
    log_warning "Cleanup initiated..."
    
    if [ -n "$SSH_PID" ] && kill -0 "$SSH_PID" 2>/dev/null; then
        log_info "Terminating remote TCP server (PID: $SSH_PID)..."
        # Send Ctrl+C to the SSH session
        kill -INT "$SSH_PID" 2>/dev/null || true
        sleep 2
        # Force kill if still running
        if kill -0 "$SSH_PID" 2>/dev/null; then
            kill -KILL "$SSH_PID" 2>/dev/null || true
        fi
        log_success "Remote TCP server terminated"
    fi
    
    # Try to stop recording if it was started
    if [ "$REMOTE_ONLY" = false ]; then
        log_info "Ensuring recording is stopped..."
        mosquitto_pub -h "$HOST" -t "$MQTT_CONTROL_TOPIC" -m "record_off" -q 1 2>/dev/null || true
    fi
    
    if [ $exit_code -ne 0 ]; then
        log_error "Script exited with error code: $exit_code"
    fi
}

# Register cleanup on exit
trap cleanup EXIT INT TERM

# ==================== Helper Functions ====================
check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "Required command not found: $1"
        exit 1
    fi
}

wait_with_spinner() {
    local duration=$1
    local message=$2
    local pid=$!
    
    echo -n "$message"
    for ((i=0; i<duration; i++)); do
        sleep 1
        echo -n "."
    done
    echo " done"
}

test_ssh_connection() {
    log_info "Testing SSH connection to ${REMOTE_USER}@${HOST}..."
    if ssh -o ConnectTimeout=5 -o BatchMode=yes "${REMOTE_USER}@${HOST}" "echo 'Connection successful'" &>/dev/null; then
        log_success "SSH connection verified"
        return 0
    else
        log_error "Cannot connect to ${REMOTE_USER}@${HOST}"
        log_warning "Ensure SSH keys are set up or use ssh-copy-id"
        return 1
    fi
}

test_mqtt_connection() {
    log_info "Testing MQTT connection to $HOST..."
    if mosquitto_pub -h "$HOST" -t "test/connection" -m "test" -q 0 2>/dev/null; then
        log_success "MQTT connection verified"
        return 0
    else
        log_error "Cannot connect to MQTT broker at $HOST"
        return 1
    fi
}

# ==================== Check Dependencies ====================
log_info "Checking dependencies..."
check_command "ssh"
check_command "mosquitto_pub"
check_command "rsync"
if [ "$REMOTE_ONLY" = false ]; then
    check_command "python3"
fi
log_success "All dependencies available"

# ==================== Test Connections ====================
test_ssh_connection || exit 1
test_mqtt_connection || exit 1

# ==================== Main Workflow ====================
log_info "========================================"
log_info "Starting Calibration Workflow"
log_info "========================================"
log_info "Host: $HOST"
log_info "Recording: $RECORDING_NAME"
log_info "Pulse pattern: $PULSE_PATTERN"
log_info "Delay after pulses: ${DELAY_AFTER_PULSES}s"
log_info "========================================"

# Step 1: Launch TCP Server on Remote Host
log_info "Step 1: Launching TCP server on remote host..."
log_info "Remote path: ${REMOTE_DATA_PATH}"

# Create neural_data directory if it doesn't exist
ssh "${REMOTE_USER}@${HOST}" "mkdir -p ${REMOTE_BASE_PATH}/neural_data" || {
    log_error "Failed to create remote directory"
    exit 1
}

# Launch TCP server in background via SSH
# Use nohup and redirect to ensure it stays alive and we can see output
ssh "${REMOTE_USER}@${HOST}" "cd ${REMOTE_BASE_PATH} && python3 tcp_server.py -f neural_data/${RECORDING_FILE}" &
SSH_PID=$!

log_success "TCP server launched (PID: $SSH_PID)"
log_info "Waiting for TCP server to initialize..."
sleep 3

# Verify SSH process is still running
if ! kill -0 "$SSH_PID" 2>/dev/null; then
    log_error "TCP server failed to start"
    exit 1
fi

if [ "$REMOTE_ONLY" = true ]; then
    log_success "Remote server running. Press Ctrl+C to stop and save data."
    log_info "SSH PID: $SSH_PID"
    log_info "Waiting indefinitely..."
    wait "$SSH_PID"
    exit 0
fi

# Step 2: Start Recording
log_info "Step 2: Starting recording on neurocompressor..."
mosquitto_pub -h "$HOST" -t "$MQTT_CONTROL_TOPIC" -m "record_on" -q 1 || {
    log_error "Failed to start recording"
    exit 1
}
log_success "Recording started"
sleep 2

# Step 3: Send Test Pulses
log_info "Step 3: Sending test pulse pattern..."
log_info "Pattern: $PULSE_PATTERN"
mosquitto_pub -h "$HOST" -t "$MQTT_GENERATOR_TOPIC" -m "$PULSE_PATTERN" -q 1 || {
    log_error "Failed to send pulse pattern"
    exit 1
}
log_success "Pulse pattern sent"

# Step 4: Wait for Pulses to Complete
log_info "Step 4: Waiting for pulses to complete..."
log_info "Delay: ${DELAY_AFTER_PULSES} seconds"
sleep "$DELAY_AFTER_PULSES"

# Step 5: Stop Recording
log_info "Step 5: Stopping recording..."
mosquitto_pub -h "$HOST" -t "$MQTT_CONTROL_TOPIC" -m "record_off" -q 1 || {
    log_error "Failed to stop recording"
    exit 1
}
log_success "Recording stopped"
sleep 2

# Step 6: Terminate TCP Server (saves data)
log_info "Step 6: Terminating TCP server to save data..."
if [ -n "$SSH_PID" ] && kill -0 "$SSH_PID" 2>/dev/null; then
    kill -INT "$SSH_PID" 2>/dev/null || true
    log_info "Waiting for TCP server to save data..."
    sleep 3
    
    # Force kill if still running
    if kill -0 "$SSH_PID" 2>/dev/null; then
        log_warning "Force killing TCP server..."
        kill -KILL "$SSH_PID" 2>/dev/null || true
    fi
    SSH_PID=""  # Clear so cleanup doesn't try again
fi
log_success "TCP server terminated"

# Step 7: Verify Remote File Exists
log_info "Step 7: Verifying remote data file..."
if ssh "${REMOTE_USER}@${HOST}" "test -f ${REMOTE_DATA_PATH}"; then
    FILE_SIZE=$(ssh "${REMOTE_USER}@${HOST}" "stat -f%z ${REMOTE_DATA_PATH} 2>/dev/null || stat -c%s ${REMOTE_DATA_PATH}")
    log_success "Remote file exists (${FILE_SIZE} bytes)"
else
    log_error "Remote file not found: ${REMOTE_DATA_PATH}"
    log_warning "Check TCP server logs for errors"
    exit 1
fi

# Step 8: Download Data
log_info "Step 8: Downloading data from remote host..."
log_info "Remote: ${REMOTE_USER}@${HOST}:${REMOTE_DATA_PATH}"
log_info "Local: ${LOCAL_DATA_PATH}"

rsync -avz --progress "${REMOTE_USER}@${HOST}:${REMOTE_DATA_PATH}" "${LOCAL_DATA_PATH}" || {
    log_error "Failed to download data file"
    exit 1
}

if [ -f "$LOCAL_DATA_PATH" ]; then
    LOCAL_SIZE=$(stat -f%z "$LOCAL_DATA_PATH" 2>/dev/null || stat -c%s "$LOCAL_DATA_PATH")
    log_success "Data downloaded successfully (${LOCAL_SIZE} bytes)"
else
    log_error "Downloaded file not found at ${LOCAL_DATA_PATH}"
    exit 1
fi

# Step 9: Verify JSON Format
log_info "Step 9: Verifying JSON format..."
if python3 -m json.tool "$LOCAL_DATA_PATH" > /dev/null 2>&1; then
    log_success "JSON format valid"
else
    log_error "Invalid JSON format in downloaded file"
    exit 1
fi

# Step 10: Generate Report
log_info "Step 10: Generating analysis report..."
log_info "Input: ${LOCAL_DATA_PATH}"
log_info "Output: ${LOCAL_REPORT_PATH}"

# Check if report generator script exists
REPORT_SCRIPT="dataset_report_generator.py"
if [ -f "$SCRIPT_DIR/$REPORT_SCRIPT" ]; then
    REPORT_SCRIPT_PATH="$SCRIPT_DIR/$REPORT_SCRIPT"
elif [ -f "$REPORT_SCRIPT" ]; then
    REPORT_SCRIPT_PATH="$REPORT_SCRIPT"
elif command -v dataset_report_generator.py &> /dev/null; then
    REPORT_SCRIPT_PATH="dataset_report_generator.py"
else
    log_error "Report generator script not found: $REPORT_SCRIPT"
    log_warning "Please ensure dataset_report_generator.py is in the same directory as this script"
    log_warning "Data has been downloaded to: ${LOCAL_DATA_PATH}"
    exit 1
fi

python3 "$REPORT_SCRIPT_PATH" --input "$LOCAL_DATA_PATH" --output "$LOCAL_REPORT_PATH" || {
    log_error "Failed to generate report"
    log_warning "Data has been downloaded to: ${LOCAL_DATA_PATH}"
    exit 1
}

if [ -f "$LOCAL_REPORT_PATH" ]; then
    REPORT_SIZE=$(stat -f%z "$LOCAL_REPORT_PATH" 2>/dev/null || stat -c%s "$LOCAL_REPORT_PATH")
    log_success "Report generated successfully (${REPORT_SIZE} bytes)"
else
    log_error "Report file not found at ${LOCAL_REPORT_PATH}"
    exit 1
fi

# ==================== Summary ====================
echo ""
log_success "========================================"
log_success "Calibration Complete!"
log_success "========================================"
log_info "Data file: ${LOCAL_DATA_PATH}"
log_info "Report: ${LOCAL_REPORT_PATH}"
log_info "Recording name: ${RECORDING_NAME}"
log_info "Host: ${HOST}"
log_success "========================================"
echo ""