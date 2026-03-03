#!/usr/bin/env bash
set -euo pipefail

PROJECT="crypto-signal-bot"
COMPOSE="docker compose"

# ── Colors ──────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── Commands ────────────────────────────────────────────

cmd_build() {
    info "Building Docker images..."
    $COMPOSE build "$@"
    ok "Build complete"
}

cmd_start() {
    info "Starting services..."
    $COMPOSE up -d "$@"
    ok "Services started"
    cmd_status
}

cmd_stop() {
    info "Stopping services..."
    $COMPOSE down "$@"
    ok "Services stopped"
}

cmd_restart() {
    info "Restarting services..."
    $COMPOSE restart "$@"
    ok "Services restarted"
}

cmd_logs() {
    local svc="${1:-}"
    if [[ -n "$svc" ]]; then
        $COMPOSE logs -f "$svc"
    else
        $COMPOSE logs -f
    fi
}

cmd_test() {
    info "Running tests in container..."
    $COMPOSE run --rm --no-deps \
        -v "$(pwd)/tests:/app/tests" \
        -v "$(pwd)/docs:/app/docs" \
        --entrypoint pytest bot tests/ -v "$@"
}

cmd_lint() {
    info "Running black --check..."
    $COMPOSE run --rm --no-deps \
        --entrypoint black bot --check custom/ tests/ main.py "$@"
}

cmd_shell() {
    info "Opening shell in bot container..."
    $COMPOSE run --rm --entrypoint /bin/bash bot
}

cmd_db_init() {
    info "Initializing database..."
    $COMPOSE run --rm --no-deps \
        --entrypoint python bot -c "from custom.utils.db import init_db; init_db('data/signals.db'); print('DB initialized')"
    ok "Database initialized"
}

cmd_status() {
    echo ""
    info "Container status:"
    $COMPOSE ps
    echo ""

    # Show DB size if data volume exists
    local db_size
    db_size=$($COMPOSE run --rm --no-deps --entrypoint sh bot -c \
        'if [ -f data/signals.db ]; then du -h data/signals.db | cut -f1; else echo "not found"; fi' 2>/dev/null || echo "n/a")
    info "Database size: ${db_size}"
    echo ""
}

cmd_setup() {
    info "First-time setup..."

    if [[ ! -f .env ]]; then
        if [[ -f .env.example ]]; then
            cp .env.example .env
            ok "Created .env from .env.example — edit it with your API keys"
        else
            err ".env.example not found"
            exit 1
        fi
    else
        warn ".env already exists, skipping"
    fi

    cmd_build
    ok "Setup complete. Edit .env then run: ./run.sh start"
}

cmd_help() {
    cat <<EOF

${CYAN}${PROJECT}${NC} — helper script

Usage: ./run.sh <command> [args]

Commands:
  build          Build Docker images
  start          Start bot + dashboard
  stop           Stop all services
  restart        Restart services
  logs [svc]     Tail logs (bot or dashboard)
  test           Run pytest in container
  lint           Run black --check
  shell          Open shell in bot container
  db-init        Initialize database
  status         Show running containers + DB size
  setup          First-time setup: copy .env.example, build

EOF
}

# ── Dispatch ────────────────────────────────────────────

cmd="${1:-help}"
shift 2>/dev/null || true

case "$cmd" in
    build)    cmd_build "$@" ;;
    start)    cmd_start "$@" ;;
    stop)     cmd_stop "$@" ;;
    restart)  cmd_restart "$@" ;;
    logs)     cmd_logs "$@" ;;
    test)     cmd_test "$@" ;;
    lint)     cmd_lint "$@" ;;
    shell)    cmd_shell ;;
    db-init)  cmd_db_init ;;
    status)   cmd_status ;;
    setup)    cmd_setup ;;
    help|-h|--help) cmd_help ;;
    *)
        err "Unknown command: $cmd"
        cmd_help
        exit 1
        ;;
esac
