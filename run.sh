#!/usr/bin/env bash
set -euo pipefail

PROJECT="crypto-signal-bot"
COMPOSE="docker compose"

# ── VPS Settings (used by clone command) ─────────────────
VPS_HOST="${VPS_HOST:-myvps}"              # SSH config host name
VPS_PROJECT_DIR="${VPS_PROJECT_DIR:-/opt/crypto-signal-bot}"  # Remote project path
CLONE_DIR="./backup"                       # Local backup destination

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

cmd_preflight() {
    info "Running preflight health check..."
    $COMPOSE run --rm \
        --entrypoint python bot main.py --preflight
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

cmd_deploy() {
    info "Deploying to VPS (${VPS_HOST}:${VPS_PROJECT_DIR})..."

    # ── 1. Dry-run first ──
    info "Checking what will be synced (dry-run)..."
    echo ""
    rsync -avzn --delete \
        --exclude='.git/' \
        --exclude='.env' \
        --exclude='.env.*' \
        --exclude='data/*.db' \
        --exclude='data/*.db-journal' \
        --exclude='data/*.db-wal' \
        --exclude='backup/' \
        --exclude='__pycache__/' \
        --exclude='*.pyc' \
        --exclude='.pytest_cache/' \
        --exclude='.mypy_cache/' \
        --exclude='htmlcov/' \
        --exclude='.coverage' \
        --exclude='.venv/' \
        --exclude='venv/' \
        --exclude='.DS_Store' \
        --exclude='.claude/memory/' \
        --exclude='logs/' \
        --exclude='*.log' \
        --exclude='freqtrade/user_data/data/' \
        --exclude='freqtrade/user_data/logs/' \
        --exclude='freqtrade/user_data/backtest_results/' \
        ./ "${VPS_HOST}:${VPS_PROJECT_DIR}/"
    echo ""

    # ── 2. Confirm ──
    read -rp "$(echo -e "${YELLOW}Proceed with deploy? [y/N]${NC} ")" confirm
    if [[ "${confirm}" != "y" && "${confirm}" != "Y" ]]; then
        warn "Deploy cancelled"
        return
    fi

    # ── 3. Rsync ──
    info "Syncing files..."
    rsync -avz --delete \
        --exclude='.git/' \
        --exclude='.env' \
        --exclude='.env.*' \
        --exclude='data/*.db' \
        --exclude='data/*.db-journal' \
        --exclude='data/*.db-wal' \
        --exclude='backup/' \
        --exclude='__pycache__/' \
        --exclude='*.pyc' \
        --exclude='.pytest_cache/' \
        --exclude='.mypy_cache/' \
        --exclude='htmlcov/' \
        --exclude='.coverage' \
        --exclude='.venv/' \
        --exclude='venv/' \
        --exclude='.DS_Store' \
        --exclude='.claude/memory/' \
        --exclude='logs/' \
        --exclude='*.log' \
        --exclude='freqtrade/user_data/data/' \
        --exclude='freqtrade/user_data/logs/' \
        --exclude='freqtrade/user_data/backtest_results/' \
        ./ "${VPS_HOST}:${VPS_PROJECT_DIR}/"
    ok "Files synced"

    # ── 4. Rebuild & restart ──
    info "Rebuilding and restarting on VPS..."
    ssh "${VPS_HOST}" "cd ${VPS_PROJECT_DIR} && docker compose build && docker compose up -d"
    ok "Services restarted"

    # ── 5. Verify ──
    info "Verifying deployment..."
    ssh "${VPS_HOST}" "cd ${VPS_PROJECT_DIR} && docker compose ps"
    echo ""
    ok "Deploy complete"
}

cmd_clone() {
    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)
    local dest="${CLONE_DIR}/${timestamp}"

    info "Cloning data from VPS (${VPS_HOST}:${VPS_PROJECT_DIR})..."
    info "Destination: ${dest}"
    mkdir -p "${dest}"

    # ── 1. Database ──
    info "Syncing database..."
    mkdir -p "${dest}/data"
    rsync -avz --progress \
        "${VPS_HOST}:${VPS_PROJECT_DIR}/data/signals.db" \
        "${dest}/data/" 2>/dev/null && ok "Database synced" || warn "Database not found or sync failed"

    # ── 2. Config files ──
    info "Syncing config..."
    mkdir -p "${dest}/config"
    rsync -avz --progress \
        "${VPS_HOST}:${VPS_PROJECT_DIR}/config/settings.yaml" \
        "${dest}/config/" 2>/dev/null && ok "settings.yaml synced" || warn "settings.yaml not found"

    rsync -avz --progress \
        "${VPS_HOST}:${VPS_PROJECT_DIR}/.env" \
        "${dest}/" 2>/dev/null && ok ".env synced" || warn ".env not found"

    # ── 3. Docker logs ──
    info "Fetching docker logs..."
    mkdir -p "${dest}/logs"
    ssh "${VPS_HOST}" "cd ${VPS_PROJECT_DIR} && docker compose logs --no-color --tail=5000" \
        > "${dest}/logs/docker_all.log" 2>/dev/null && ok "Docker logs saved" || warn "Could not fetch docker logs"

    ssh "${VPS_HOST}" "cd ${VPS_PROJECT_DIR} && docker compose logs --no-color --tail=5000 bot" \
        > "${dest}/logs/docker_bot.log" 2>/dev/null && ok "Bot logs saved" || warn "Could not fetch bot logs"

    # ── Summary ──
    echo ""
    ok "Clone complete → ${dest}"
    info "Contents:"
    find "${dest}" -type f -exec du -h {} \; | sort -rh
    echo ""

    # ── Symlink latest ──
    ln -sfn "${timestamp}" "${CLONE_DIR}/latest"
    info "Symlink: ${CLONE_DIR}/latest → ${timestamp}"
}

cmd_restore() {
    local snapshot="${1:-latest}"
    local src="${CLONE_DIR}/${snapshot}"

    # Resolve "latest" symlink
    if [[ "${snapshot}" == "latest" ]]; then
        if [[ ! -L "${CLONE_DIR}/latest" ]]; then
            err "No backups found. Run './run.sh clone' first."
            exit 1
        fi
        src=$(readlink -f "${CLONE_DIR}/latest")
    fi

    if [[ ! -d "${src}" ]]; then
        err "Backup not found: ${src}"
        info "Available backups:"
        cmd_backups
        exit 1
    fi

    info "Restoring from: ${src}"
    echo ""

    # ── 1. Database ──
    if [[ -f "${src}/data/signals.db" ]]; then
        if [[ -f "data/signals.db" ]]; then
            local bak="data/signals.db.bak.$(date +%Y%m%d_%H%M%S)"
            warn "Existing local DB backed up → ${bak}"
            cp "data/signals.db" "${bak}"
        fi
        mkdir -p data
        cp "${src}/data/signals.db" "data/signals.db"
        ok "Database restored ($(du -h data/signals.db | cut -f1))"
    else
        warn "No database in backup, skipping"
    fi

    # ── 2. Config ──
    if [[ -f "${src}/config/settings.yaml" ]]; then
        cp "${src}/config/settings.yaml" "config/settings.yaml"
        ok "config/settings.yaml restored"
    fi

    if [[ -f "${src}/.env" ]]; then
        if [[ -f ".env" ]]; then
            warn "Existing .env backed up → .env.bak"
            cp ".env" ".env.bak"
        fi
        cp "${src}/.env" ".env"
        ok ".env restored"
    fi

    echo ""
    ok "Restore complete. You can now:"
    info "  Run locally:    python main.py"
    info "  Query DB:       sqlite3 data/signals.db"
    info "  Read VPS logs:  cat ${src}/logs/docker_bot.log"
}

cmd_backups() {
    if [[ ! -d "${CLONE_DIR}" ]]; then
        warn "No backups directory found. Run './run.sh clone' first."
        return
    fi

    local latest_target=""
    if [[ -L "${CLONE_DIR}/latest" ]]; then
        latest_target=$(readlink "${CLONE_DIR}/latest")
    fi

    info "Available backups in ${CLONE_DIR}/:"
    echo ""
    for dir in "${CLONE_DIR}"/20*; do
        [[ -d "$dir" ]] || continue
        local name
        name=$(basename "$dir")
        local size
        size=$(du -sh "$dir" 2>/dev/null | cut -f1)
        local marker=""
        if [[ "${name}" == "${latest_target}" ]]; then
            marker=" ${GREEN}← latest${NC}"
        fi
        echo -e "  ${name}  (${size})${marker}"
    done
    echo ""
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
  preflight      Run preflight health check (test API connections)
  db-init        Initialize database
  status         Show running containers + DB size
  setup          First-time setup: copy .env.example, build
  deploy         Deploy code to VPS (rsync + rebuild + restart)
  clone          Clone DB, config & logs from VPS to local backup/
  restore [ts]   Restore backup to local project (default: latest)
  backups        List all available backups

  VPS settings (env vars or edit run.sh):
    VPS_HOST          SSH config host name   (default: myvps)
    VPS_PROJECT_DIR   Remote project path    (default: /opt/crypto-signal-bot)

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
    preflight) cmd_preflight ;;
    db-init)  cmd_db_init ;;
    status)   cmd_status ;;
    setup)    cmd_setup ;;
    deploy)   cmd_deploy ;;
    clone)    cmd_clone ;;
    restore)  cmd_restore "$@" ;;
    backups)  cmd_backups ;;
    help|-h|--help) cmd_help ;;
    *)
        err "Unknown command: $cmd"
        cmd_help
        exit 1
        ;;
esac
