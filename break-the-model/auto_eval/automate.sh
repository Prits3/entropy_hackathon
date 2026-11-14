#!/bin/bash
# AutoEval Automation Scripts
# Run automated attack sweeps, training cycles, and continuous monitoring

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS_DIR="${SCRIPT_DIR}/logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

usage() {
    echo "AutoEval Automation Suite"
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  sweep              Run full attack sweep across all models"
    echo "  single <technique> Run a single technique test on all models"
    echo "  train              Run training cycle and generate improvements"
    echo "  monitor <file>     Monitor results file in real-time"
    echo "  report             Generate comprehensive HTML report"
    echo "  clean              Clean old log files"
    echo ""
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Ensure logs directory exists
mkdir -p "$LOGS_DIR"

cmd_sweep() {
    log_info "Starting full attack sweep..."
    
    python3 "${SCRIPT_DIR}/runner.py" sweep \
        --test-file "${SCRIPT_DIR}/tests.json" \
        --all-models \
        --output-dir "$LOGS_DIR" \
        --timestamp "$TIMESTAMP"
    
    log_success "Sweep complete. Results saved to $LOGS_DIR/metrics_${TIMESTAMP}.json"
}

cmd_single() {
    if [ -z "$1" ]; then
        log_error "Please specify a technique (e.g., L1_DIRECT)"
        exit 1
    fi
    
    local TECH=$1
    shift
    TECH_ARGS="--technique $TECH"
    
    log_info "Running single technique test: $TECH"
    
    python3 "${SCRIPT_DIR}/runner.py" test \
        $TECH_ARGS \
        --all-models \
        --output-dir "$LOGS_DIR" \
        --timestamp "$TIMESTAMP"
    
    log_success "Single technique test complete"
}

cmd_train() {
    log_info "Running training cycle..."
    
    if [ -z "$1" ]; then
        log_error "Please specify a timestamp (e.g., 20240115_143022)"
        exit 1
    fi
    
    local TS=$1
    
    python3 "${SCRIPT_DIR}/trainer.py" \
        --output-dir "$LOGS_DIR" \
        --timestamp "$TS"
    
    log_success "Training cycle complete. Improvements generated."
}

cmd_monitor() {
    log_info "Starting live AutoEval dashboard server..."
    
    python3 "${SCRIPT_DIR}/dashboard.py" \
        --serve \
        --no-open
}

cmd_report() {
    log_info "Generating comprehensive HTML report..."
    
    local REPORT_FILE="${SCRIPT_DIR}/dashboard.html"
    python3 "${SCRIPT_DIR}/runner.py" report \
        --output "$REPORT_FILE"
    
    log_success "Report saved to $REPORT_FILE"
}

cmd_clean() {
    log_info "Cleaning old log files (keeping last 20)..."
    
    # Find and remove old JSON files
    find "$LOGS_DIR" -name "*.json" -type f -mtime +7 | head -n -20 | xargs rm -f 2>/dev/null || true
    
    log_success "Cleanup complete"
}

# Main entry point
if [ $# -eq 0 ]; then
    usage
    exit 1
fi

COMMAND=$1
shift

case "$COMMAND" in
    sweep)
        cmd_sweep $@
        ;;
    single)
        cmd_single $@
        ;;
    train)
        cmd_train $@
        ;;
    monitor)
        cmd_monitor $@
        ;;
    report)
        cmd_report $@
        ;;
    clean)
        cmd_clean $@
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        log_error "Unknown command: $COMMAND"
        usage
        exit 1
        ;;
esac
