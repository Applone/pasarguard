#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
#  patch.sh – Safely patch an existing PasarGuard installation to use
#             the latest image from the Applone/pasarguard fork on GHCR.
#
#  Usage:
#    sudo bash patch.sh [OPTIONS]
#
#  Options:
#    --install-dir DIR    Application directory  (default: /opt/pasarguard)
#    --data-dir DIR       Persistent data dir    (default: /var/lib/pasarguard)
#    --tag TAG            Image tag to pull       (default: dev)
#    --no-backup          Skip pre-patch backup
#    --dry-run            Show what would happen without making changes
#    --yes                Skip confirmation prompts
#    -h, --help           Show this help message
#
#  The script will:
#    1. Detect the deployment type (Docker or bare-metal/systemd)
#    2. Create a backup of the install directory and database
#    3. Stop the running service
#    4. Docker: swap the image to ghcr.io/applone/pasarguard and pull it
#       Bare-metal: pull source from the fork via git
#    5. Apply database migrations and sync dependencies (bare-metal)
#    6. Restart the service
#    7. Run a health check to verify the patch
#
#  Rollback: If any critical step fails, the script automatically
#            restores from backup and restarts the original version.
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────
INSTALL_DIR="/opt/pasarguard"
DATA_DIR="/var/lib/pasarguard"
FORK_REPO="https://github.com/Applone/pasarguard.git"
FORK_IMAGE="ghcr.io/applone/pasarguard"
IMAGE_TAG="dev"
CREATE_BACKUP=true
DRY_RUN=false
AUTO_YES=false

# ── Colors ───────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ── Logging ──────────────────────────────────────────────────────────
log_info()    { echo -e "${BLUE}[INFO]${NC}    $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}      $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}    $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC}   $*"; }
log_step()    { echo -e "\n${BOLD}${CYAN}▸ $*${NC}"; }
log_dry()     { echo -e "${YELLOW}[DRY-RUN]${NC} $*"; }

die() { log_error "$@"; exit 1; }

# ── Usage ────────────────────────────────────────────────────────────
usage() {
    sed -n '/^#  Usage:/,/^# ──/p' "$0" | head -n -1 | sed 's/^#//'
    exit 0
}

# ── Parse Arguments ──────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --install-dir)   INSTALL_DIR="$2"; shift 2 ;;
        --data-dir)      DATA_DIR="$2"; shift 2 ;;
        --tag)           IMAGE_TAG="$2"; shift 2 ;;
        --no-backup)     CREATE_BACKUP=false; shift ;;
        --dry-run)       DRY_RUN=true; shift ;;
        --yes|-y)        AUTO_YES=true; shift ;;
        -h|--help)       usage ;;
        *)               die "Unknown option: $1. Use --help for usage." ;;
    esac
done

# ── Derived Paths ────────────────────────────────────────────────────
COMPOSE_FILE="${INSTALL_DIR}/docker-compose.yml"
ENV_FILE="${INSTALL_DIR}/.env"
SERVICE_NAME="pasarguard"
BACKUP_DIR=""
BACKUP_TIMESTAMP=""
DEPLOY_TYPE=""        # "docker" or "bare-metal"
ORIGINAL_IMAGE=""     # recorded for rollback (Docker)
PRE_PATCH_COMMIT=""   # recorded for rollback (bare-metal)

# ── Helper Functions ─────────────────────────────────────────────────

confirm() {
    if $AUTO_YES; then return 0; fi
    local prompt="${1:-Continue?}"
    echo -en "${BOLD}${prompt} [y/N]: ${NC}"
    read -r answer
    case "$answer" in
        [yY]|[yY][eE][sS]) return 0 ;;
        *) die "Aborted by user." ;;
    esac
}

require_cmd() {
    local cmd="$1"
    local hint="${2:-}"
    if ! command -v "$cmd" &>/dev/null; then
        if [[ -n "$hint" ]]; then
            die "'$cmd' is required but not found. $hint"
        else
            die "'$cmd' is required but not found."
        fi
    fi
}

detect_deploy_type() {
    if [[ -f "$COMPOSE_FILE" ]] && command -v docker &>/dev/null; then
        DEPLOY_TYPE="docker"
    elif systemctl list-unit-files "${SERVICE_NAME}.service" &>/dev/null 2>&1 && \
         [[ -f "${INSTALL_DIR}/main.py" ]]; then
        DEPLOY_TYPE="bare-metal"
    elif [[ -f "${INSTALL_DIR}/main.py" ]]; then
        DEPLOY_TYPE="bare-metal"
    else
        die "Could not detect PasarGuard deployment at ${INSTALL_DIR}."
    fi
}

# Get the current image from docker-compose.yml
get_current_image() {
    grep -E '^\s*image:' "$COMPOSE_FILE" 2>/dev/null | head -1 | sed 's/.*image:\s*//' | tr -d ' "'"'" || echo "unknown"
}

get_current_commit() {
    if [[ -d "${INSTALL_DIR}/.git" ]]; then
        git -C "$INSTALL_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown"
    else
        echo "unknown"
    fi
}

# ── Service Control ──────────────────────────────────────────────────

stop_service() {
    log_step "Stopping PasarGuard service"
    if $DRY_RUN; then log_dry "Would stop ${DEPLOY_TYPE} service"; return 0; fi

    if [[ "$DEPLOY_TYPE" == "docker" ]]; then
        if docker compose -f "$COMPOSE_FILE" -p "$SERVICE_NAME" ps --quiet 2>/dev/null | grep -q .; then
            docker compose -f "$COMPOSE_FILE" -p "$SERVICE_NAME" stop --timeout 30 2>/dev/null || \
                docker-compose -f "$COMPOSE_FILE" -p "$SERVICE_NAME" stop --timeout 30 2>/dev/null || true
            log_success "Docker containers stopped"
        else
            log_info "Docker containers are not running"
        fi
    else
        if systemctl is-active --quiet "${SERVICE_NAME}.service" 2>/dev/null; then
            systemctl stop "${SERVICE_NAME}.service"
            local i=0
            while systemctl is-active --quiet "${SERVICE_NAME}.service" 2>/dev/null && [[ $i -lt 15 ]]; do
                sleep 1; ((i++))
            done
            log_success "systemd service stopped"
        else
            log_info "Service is not running"
        fi
    fi
}

start_service() {
    log_step "Starting PasarGuard service"
    if $DRY_RUN; then log_dry "Would start ${DEPLOY_TYPE} service"; return 0; fi

    if [[ "$DEPLOY_TYPE" == "docker" ]]; then
        docker compose -f "$COMPOSE_FILE" -p "$SERVICE_NAME" up -d 2>/dev/null || \
            docker-compose -f "$COMPOSE_FILE" -p "$SERVICE_NAME" up -d
        log_success "Docker containers started"
    else
        if systemctl list-unit-files "${SERVICE_NAME}.service" &>/dev/null 2>&1; then
            systemctl daemon-reload
            systemctl start "${SERVICE_NAME}.service"
            log_success "systemd service started"
        else
            log_warn "No systemd service found. Start manually: cd ${INSTALL_DIR} && bash start.sh"
        fi
    fi
}

# ── Backup ───────────────────────────────────────────────────────────

create_backup() {
    if ! $CREATE_BACKUP; then
        log_info "Backup skipped (--no-backup)"
        return 0
    fi

    log_step "Creating backup"
    BACKUP_TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
    BACKUP_DIR="${DATA_DIR}/backups/patch_${BACKUP_TIMESTAMP}"

    if $DRY_RUN; then log_dry "Would create backup at ${BACKUP_DIR}"; return 0; fi

    mkdir -p "$BACKUP_DIR"

    # Backup the install directory (exclude heavy generated dirs)
    log_info "Backing up ${INSTALL_DIR} → ${BACKUP_DIR}/app/"
    rsync -a \
        --exclude='.venv' \
        --exclude='node_modules' \
        --exclude='__pycache__' \
        --exclude='.ruff_cache' \
        --exclude='.pytest_cache' \
        "${INSTALL_DIR}/" "${BACKUP_DIR}/app/" 2>/dev/null || \
        cp -a "${INSTALL_DIR}" "${BACKUP_DIR}/app" 2>/dev/null || \
        die "Failed to backup install directory"

    # Backup .env separately for easy access
    if [[ -f "$ENV_FILE" ]]; then
        cp -p "$ENV_FILE" "${BACKUP_DIR}/env.backup"
    fi

    # Backup SQLite database if present
    if [[ -f "${INSTALL_DIR}/db.sqlite3" ]]; then
        log_info "Backing up SQLite database"
        cp -p "${INSTALL_DIR}/db.sqlite3" "${BACKUP_DIR}/db.sqlite3.backup"
    fi

    # Record state for rollback
    if [[ "$DEPLOY_TYPE" == "docker" ]]; then
        echo "$ORIGINAL_IMAGE" > "${BACKUP_DIR}/original_image.txt"
    else
        echo "$PRE_PATCH_COMMIT" > "${BACKUP_DIR}/pre_patch_commit.txt"
    fi

    log_success "Backup created at ${BACKUP_DIR}"
}

# ── Rollback ─────────────────────────────────────────────────────────

rollback() {
    log_error "Patch failed! Initiating rollback..."

    if [[ -z "$BACKUP_DIR" ]] || [[ ! -d "${BACKUP_DIR}/app" ]]; then
        die "No backup available for rollback. Manual intervention required.
    Install directory: ${INSTALL_DIR}"
    fi

    log_step "Restoring from backup"

    if [[ "$DEPLOY_TYPE" == "docker" ]]; then
        # Restore docker-compose.yml (which contains the original image)
        if [[ -f "${BACKUP_DIR}/app/docker-compose.yml" ]]; then
            cp -p "${BACKUP_DIR}/app/docker-compose.yml" "$COMPOSE_FILE"
            log_info "Restored original docker-compose.yml"
        fi
    else
        rsync -a --delete \
            --exclude='.venv' \
            --exclude='node_modules' \
            "${BACKUP_DIR}/app/" "${INSTALL_DIR}/" 2>/dev/null || \
            die "Rollback failed! Manual restore needed from: ${BACKUP_DIR}/app/"

        if [[ -f "${BACKUP_DIR}/db.sqlite3.backup" ]]; then
            cp -p "${BACKUP_DIR}/db.sqlite3.backup" "${INSTALL_DIR}/db.sqlite3"
        fi
    fi

    if [[ -f "${BACKUP_DIR}/env.backup" ]]; then
        cp -p "${BACKUP_DIR}/env.backup" "$ENV_FILE"
    fi

    log_success "Files restored from backup"
    start_service
    log_warn "Rolled back to pre-patch state"
    exit 1
}

# ── Docker: Swap image and pull ──────────────────────────────────────

patch_docker() {
    local new_image="${FORK_IMAGE}:${IMAGE_TAG}"

    log_step "Updating Docker image to ${new_image}"

    if [[ "$ORIGINAL_IMAGE" == "$new_image" ]]; then
        # Same image reference – just pull the latest digest
        log_info "Image reference is already ${new_image}. Pulling latest digest..."
        if $DRY_RUN; then log_dry "Would pull ${new_image}"; return 0; fi

        docker pull "$new_image" || die "Failed to pull ${new_image}"
        log_success "Pulled latest ${new_image}"
        return 0
    fi

    if $DRY_RUN; then
        log_dry "Would replace image '${ORIGINAL_IMAGE}' → '${new_image}' in docker-compose.yml"
        log_dry "Would pull ${new_image}"
        return 0
    fi

    # Pull the new image first (fail early before touching config)
    log_info "Pulling ${new_image}..."
    docker pull "$new_image" || die "Failed to pull ${new_image}. Check that the image exists on GHCR."

    # Replace the image in docker-compose.yml
    # Use a temp file + mv for atomicity
    local tmp_compose
    tmp_compose=$(mktemp)
    sed "s|^\(\s*image:\s*\).*|\1${new_image}|" "$COMPOSE_FILE" > "$tmp_compose"
    mv "$tmp_compose" "$COMPOSE_FILE"

    log_success "docker-compose.yml updated: image → ${new_image}"
}

# ── Bare-metal: Git pull from fork ───────────────────────────────────

patch_bare_metal() {
    log_step "Pulling latest source from fork (${IMAGE_TAG})"

    if $DRY_RUN; then
        log_dry "Would fetch and checkout applone-fork/${IMAGE_TAG}"
        return 0
    fi

    cd "$INSTALL_DIR"
    require_cmd git "Install with: apt install git"

    if [[ ! -d ".git" ]]; then
        die "${INSTALL_DIR} is not a git repository. Cannot patch bare-metal install without git."
    fi

    # Add or update the fork remote
    local remote_name="applone-fork"
    if git remote get-url "$remote_name" &>/dev/null; then
        git remote set-url "$remote_name" "$FORK_REPO"
    else
        git remote add "$remote_name" "$FORK_REPO"
    fi

    # Fetch
    log_info "Fetching from ${remote_name}..."
    git fetch "$remote_name" "$IMAGE_TAG" || die "Failed to fetch from fork."

    local target_commit
    target_commit=$(git rev-parse --short "${remote_name}/${IMAGE_TAG}")

    if [[ "$PRE_PATCH_COMMIT" == "$target_commit" ]]; then
        log_success "Already up-to-date (${target_commit}). Nothing to patch."
        exit 0
    fi

    log_info "Current: ${PRE_PATCH_COMMIT} → Target: ${target_commit}"

    # Stash local changes
    local stash_needed=false
    if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
        log_warn "Local modifications detected – stashing"
        git stash push -m "patch.sh auto-stash $(date +%Y%m%d_%H%M%S)" --include-untracked
        stash_needed=true
    fi

    git checkout -B "patched-${IMAGE_TAG}" "${remote_name}/${IMAGE_TAG}"
    log_success "Source updated to ${target_commit}"

    if $stash_needed; then
        git stash pop 2>/dev/null || \
            log_warn "Could not auto-apply stashed changes. Check 'git stash list'."
    fi

    # Sync Python dependencies
    log_step "Syncing Python dependencies"
    if ! command -v uv &>/dev/null; then
        log_info "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.cargo/bin:$PATH"
    fi

    uv sync --frozen 2>/dev/null || uv sync || die "Failed to sync Python dependencies"
    log_success "Python dependencies synced"

    # Run database migrations
    log_step "Running database migrations"
    if [[ -f "$ENV_FILE" ]]; then
        set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
    fi

    if command -v uv &>/dev/null; then
        uv run alembic upgrade head || die "Database migration failed"
    elif [[ -f "${INSTALL_DIR}/.venv/bin/python3" ]]; then
        "${INSTALL_DIR}/.venv/bin/python3" -m alembic upgrade head || die "Database migration failed"
    else
        die "Cannot run migrations: neither 'uv' nor a virtualenv found"
    fi
    log_success "Database migrations completed"

    # Rebuild dashboard
    log_step "Rebuilding dashboard frontend"
    if ! command -v bun &>/dev/null; then
        log_info "Installing bun..."
        curl -fsSL https://bun.sh/install | bash
        export PATH="$HOME/.bun/bin:$PATH"
    fi

    if [[ -f "${INSTALL_DIR}/build_dashboard.sh" ]]; then
        bash "${INSTALL_DIR}/build_dashboard.sh" || die "Dashboard build failed"
    elif [[ -d "${INSTALL_DIR}/dashboard" ]]; then
        cd "${INSTALL_DIR}/dashboard"
        bun install || die "Failed to install frontend dependencies"
        VITE_BASE_API=/ bun run build || die "Dashboard build failed"
        cp ./build/index.html ./build/404.html 2>/dev/null || true
    fi
    log_success "Dashboard rebuilt"
}

# ── .env key check ───────────────────────────────────────────────────

check_new_env_keys() {
    log_step "Checking for new configuration keys"
    if $DRY_RUN; then log_dry "Would compare .env with .env.example"; return 0; fi

    local example_env="${INSTALL_DIR}/.env.example"
    [[ -f "$example_env" ]] || return 0
    [[ -f "$ENV_FILE" ]]    || return 0

    local new_keys=()
    while IFS= read -r line; do
        [[ "$line" =~ ^#.*$ ]] && continue
        [[ -z "${line// }" ]] && continue
        local key
        key=$(echo "$line" | sed 's/^\s*//;s/\s*=.*//')
        [[ -z "$key" ]] && continue
        if ! grep -qE "^\s*#?\s*${key}\s*=" "$ENV_FILE" 2>/dev/null; then
            new_keys+=("$key")
        fi
    done < "$example_env"

    if [[ ${#new_keys[@]} -gt 0 ]]; then
        log_warn "New configuration keys found in .env.example:"
        for key in "${new_keys[@]}"; do
            echo -e "  ${CYAN}${key}${NC}"
        done
        log_info "Review ${example_env} and add any you need to ${ENV_FILE}"
    else
        log_success "No new configuration keys"
    fi
}

# ── Health Check ─────────────────────────────────────────────────────

run_health_check() {
    log_step "Running health check"
    if $DRY_RUN; then log_dry "Would verify service health"; return 0; fi

    log_info "Waiting for service to start..."
    sleep 5

    local port=8000
    if [[ -f "$ENV_FILE" ]]; then
        local env_port
        env_port=$(grep -E '^\s*UVICORN_PORT\s*=' "$ENV_FILE" 2>/dev/null | tail -1 | sed 's/.*=\s*//' | tr -d ' "'"'" || true)
        if [[ -n "$env_port" ]] && [[ "$env_port" =~ ^[0-9]+$ ]]; then
            port="$env_port"
        fi
    fi

    local max_attempts=12
    local attempt=0
    local healthy=false

    while [[ $attempt -lt $max_attempts ]]; do
        ((attempt++))
        if curl -sf --max-time 5 "http://127.0.0.1:${port}/health" &>/dev/null || \
           curl -sf --max-time 5 --insecure "https://127.0.0.1:${port}/health" &>/dev/null; then
            healthy=true
            break
        fi
        log_info "Waiting... (attempt ${attempt}/${max_attempts})"
        sleep 5
    done

    if $healthy; then
        log_success "Health check passed ✓"
    else
        log_warn "Health check did not pass within 60 seconds."
        log_warn "The service may still be starting. Check logs:"
        if [[ "$DEPLOY_TYPE" == "docker" ]]; then
            log_warn "  docker compose -f ${COMPOSE_FILE} -p ${SERVICE_NAME} logs -f"
        else
            log_warn "  journalctl -u ${SERVICE_NAME}.service -f"
        fi
    fi
}

# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════

main() {
    echo -e "\n${BOLD}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}║     PasarGuard Fork Patch Script             ║${NC}"
    echo -e "${BOLD}║     ghcr.io/applone/pasarguard               ║${NC}"
    echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}\n"

    # ── Preflight ────────────────────────────────────────────────────
    log_step "Preflight checks"

    if [[ $EUID -ne 0 ]] && ! $DRY_RUN; then
        die "This script must be run as root (or with sudo)."
    fi

    if [[ ! -d "$INSTALL_DIR" ]]; then
        die "Install directory not found: ${INSTALL_DIR}
    Is PasarGuard installed? Install it first with:
    sudo bash -c \"\$(curl -fsSL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)\" @ install"
    fi

    require_cmd curl "Install with: apt install curl"

    detect_deploy_type
    log_info "Install directory:  ${INSTALL_DIR}"
    log_info "Data directory:     ${DATA_DIR}"
    log_info "Deploy type:        ${DEPLOY_TYPE}"

    if [[ "$DEPLOY_TYPE" == "docker" ]]; then
        ORIGINAL_IMAGE=$(get_current_image)
        log_info "Current image:      ${ORIGINAL_IMAGE}"
        log_info "Target image:       ${FORK_IMAGE}:${IMAGE_TAG}"
    else
        PRE_PATCH_COMMIT=$(get_current_commit)
        log_info "Current commit:     ${PRE_PATCH_COMMIT}"
        log_info "Fork branch:        ${IMAGE_TAG}"
    fi

    if $DRY_RUN; then
        echo -e "\n${YELLOW}── DRY RUN MODE: No changes will be made ──${NC}\n"
    fi

    echo ""
    confirm "Apply the Applone/pasarguard fork patch?"

    # ── Set rollback trap ────────────────────────────────────────────
    if ! $DRY_RUN; then
        trap 'rollback' ERR
    fi

    # ── Execute ──────────────────────────────────────────────────────
    create_backup
    stop_service

    if [[ "$DEPLOY_TYPE" == "docker" ]]; then
        patch_docker
    else
        patch_bare_metal
    fi

    check_new_env_keys

    # Disable ERR trap before start (start failure ≠ rollback)
    trap - ERR

    start_service
    run_health_check

    # ── Summary ──────────────────────────────────────────────────────
    echo -e "\n${BOLD}${GREEN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${GREEN}║         Patch applied successfully! ✓        ║${NC}"
    echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════╝${NC}\n"

    if [[ "$DEPLOY_TYPE" == "docker" ]]; then
        echo -e "  ${BOLD}Before:${NC}  ${ORIGINAL_IMAGE}"
        echo -e "  ${BOLD}After:${NC}   ${FORK_IMAGE}:${IMAGE_TAG}"
    else
        local new_commit
        new_commit=$(get_current_commit)
        echo -e "  ${BOLD}Before:${NC}  ${PRE_PATCH_COMMIT}"
        echo -e "  ${BOLD}After:${NC}   ${new_commit}"
        echo -e "  ${BOLD}Branch:${NC}  patched-${IMAGE_TAG}"
    fi

    if [[ -n "$BACKUP_DIR" ]] && [[ -d "$BACKUP_DIR" ]]; then
        echo -e "  ${BOLD}Backup:${NC}  ${BACKUP_DIR}"
    fi

    echo -e "\n  To revert this patch:"
    if [[ "$DEPLOY_TYPE" == "docker" ]]; then
        echo -e "    Restore ${BACKUP_DIR}/app/docker-compose.yml and restart:"
        echo -e "    cp ${BACKUP_DIR}/app/docker-compose.yml ${COMPOSE_FILE}"
        echo -e "    docker compose -f ${COMPOSE_FILE} -p ${SERVICE_NAME} up -d"
    else
        echo -e "    cd ${INSTALL_DIR} && git checkout - && sudo systemctl restart ${SERVICE_NAME}"
    fi
    echo ""
}

main "$@"
