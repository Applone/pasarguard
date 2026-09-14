#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
#  patch.sh – Safely patch or update a PasarGuard installation with
#             the Applone/pasarguard fork from GHCR.
#
#  Usage:
#    sudo bash patch.sh <patch|update> [OPTIONS]
#
#  Commands:
#    patch                Replace an upstream PasarGuard with this fork
#    update               Update an existing fork installation in-place
#
#  Options:
#    --install-dir DIR    Application directory  (default: /opt/pasarguard)
#    --data-dir DIR       Persistent data dir    (default: /var/lib/pasarguard)
#    --tag TAG            Image tag / branch      (default: dev)
#    --no-backup          Skip pre-operation backup
#    --dry-run            Show what would happen without making changes
#    --yes                Skip confirmation prompts
#    -h, --help           Show this help message
#
#  Examples:
#    sudo bash patch.sh patch                # replace upstream with fork
#    sudo bash patch.sh update               # pull latest fork image
#    sudo bash patch.sh update --tag v5.3.0  # update to a specific tag
#    bash patch.sh update --dry-run          # preview an update
#
#  Rollback: If any critical step fails, the script automatically
#            restores from backup and restarts the previous version.
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────
MODE=""  # "patch" or "update"
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
# First positional argument is the command
if [[ ${1:-} == "patch" || ${1:-} == "update" ]]; then
    MODE="$1"; shift
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        patch|update)    MODE="$1"; shift ;;
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

if [[ -z "$MODE" ]]; then
    echo -e "${RED}Error: No command specified.${NC}"
    echo -e "Usage: ${BOLD}sudo bash patch.sh <patch|update> [OPTIONS]${NC}"
    echo ""
    echo -e "  ${BOLD}patch${NC}   – Replace an upstream PasarGuard install with this fork"
    echo -e "  ${BOLD}update${NC}  – Update an existing fork installation to the latest version"
    echo ""
    echo "Run with --help for all options."
    exit 1
fi

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

get_current_branch() {
    if [[ -d "${INSTALL_DIR}/.git" ]]; then
        git -C "$INSTALL_DIR" branch --show-current 2>/dev/null || echo "unknown"
    else
        echo "unknown"
    fi
}

# Check whether the install is already running the fork
is_fork_install() {
    if [[ "$DEPLOY_TYPE" == "docker" ]]; then
        local img
        img=$(get_current_image)
        [[ "$img" == *"applone/pasarguard"* ]]
    else
        if [[ -d "${INSTALL_DIR}/.git" ]]; then
            git -C "$INSTALL_DIR" remote -v 2>/dev/null | grep -qi "applone/pasarguard"
        else
            return 1
        fi
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
    BACKUP_DIR="${DATA_DIR}/backups/${MODE}_${BACKUP_TIMESTAMP}"

    if $DRY_RUN; then log_dry "Would create backup at ${BACKUP_DIR}"; return 0; fi

    mkdir -p "$BACKUP_DIR"

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

    if [[ -f "$ENV_FILE" ]]; then
        cp -p "$ENV_FILE" "${BACKUP_DIR}/env.backup"
    fi

    if [[ -f "${INSTALL_DIR}/db.sqlite3" ]]; then
        log_info "Backing up SQLite database"
        cp -p "${INSTALL_DIR}/db.sqlite3" "${BACKUP_DIR}/db.sqlite3.backup"
    fi

    if [[ "$DEPLOY_TYPE" == "docker" ]]; then
        echo "$ORIGINAL_IMAGE" > "${BACKUP_DIR}/original_image.txt"
    else
        echo "$PRE_PATCH_COMMIT" > "${BACKUP_DIR}/pre_patch_commit.txt"
    fi

    log_success "Backup created at ${BACKUP_DIR}"
}

# ── Rollback ─────────────────────────────────────────────────────────

rollback() {
    log_error "${MODE^} failed! Initiating rollback..."

    if [[ -z "$BACKUP_DIR" ]] || [[ ! -d "${BACKUP_DIR}/app" ]]; then
        die "No backup available for rollback. Manual intervention required.
    Install directory: ${INSTALL_DIR}"
    fi

    log_step "Restoring from backup"

    if [[ "$DEPLOY_TYPE" == "docker" ]]; then
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
    log_warn "Rolled back to pre-${MODE} state"
    exit 1
}

# ══════════════════════════════════════════════════════════════════════
#  PATCH MODE – replace upstream with fork
# ══════════════════════════════════════════════════════════════════════

patch_docker() {
    local new_image="${FORK_IMAGE}:${IMAGE_TAG}"

    log_step "Switching Docker image to ${new_image}"

    if [[ "$ORIGINAL_IMAGE" == "$new_image" ]]; then
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

    log_info "Pulling ${new_image}..."
    docker pull "$new_image" || die "Failed to pull ${new_image}. Check that the image exists on GHCR."

    local tmp_compose
    tmp_compose=$(mktemp)
    sed "s|^\(\s*image:\s*\).*|\1${new_image}|" "$COMPOSE_FILE" > "$tmp_compose"
    mv "$tmp_compose" "$COMPOSE_FILE"

    log_success "docker-compose.yml updated: image → ${new_image}"
}

patch_bare_metal() {
    log_step "Pulling latest source from fork (${IMAGE_TAG})"

    if $DRY_RUN; then
        log_dry "Would fetch and checkout applone-fork/${IMAGE_TAG}"
        return 0
    fi

    cd "$INSTALL_DIR"
    require_cmd git "Install with: apt install git"

    if [[ ! -d ".git" ]]; then
        die "${INSTALL_DIR} is not a git repository. Cannot patch without git."
    fi

    local remote_name="applone-fork"
    if git remote get-url "$remote_name" &>/dev/null; then
        git remote set-url "$remote_name" "$FORK_REPO"
    else
        git remote add "$remote_name" "$FORK_REPO"
    fi

    log_info "Fetching from ${remote_name}..."
    git fetch "$remote_name" "$IMAGE_TAG" || die "Failed to fetch from fork."

    local target_commit
    target_commit=$(git rev-parse --short "${remote_name}/${IMAGE_TAG}")

    if [[ "$PRE_PATCH_COMMIT" == "$target_commit" ]]; then
        log_success "Already up-to-date (${target_commit}). Nothing to patch."
        exit 0
    fi

    log_info "Current: ${PRE_PATCH_COMMIT} → Target: ${target_commit}"

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

    bare_metal_post_update
}

# ══════════════════════════════════════════════════════════════════════
#  UPDATE MODE – pull latest version of the fork
# ══════════════════════════════════════════════════════════════════════

update_docker() {
    local current_image
    current_image=$(get_current_image)

    log_step "Pulling latest image for ${current_image}"

    if $DRY_RUN; then
        log_dry "Would pull ${current_image}"
        return 0
    fi

    # Record the old image digest for comparison
    local old_digest
    old_digest=$(docker inspect --format='{{index .RepoDigests 0}}' "$current_image" 2>/dev/null || echo "unknown")

    docker pull "$current_image" || die "Failed to pull ${current_image}"

    local new_digest
    new_digest=$(docker inspect --format='{{index .RepoDigests 0}}' "$current_image" 2>/dev/null || echo "unknown")

    if [[ "$old_digest" == "$new_digest" ]] && [[ "$old_digest" != "unknown" ]]; then
        log_success "Already running the latest image (digest unchanged)"
    else
        log_success "Pulled new image for ${current_image}"
    fi
}

update_bare_metal() {
    log_step "Pulling latest changes"

    if $DRY_RUN; then
        log_dry "Would pull latest changes on current branch"
        return 0
    fi

    cd "$INSTALL_DIR"
    require_cmd git "Install with: apt install git"

    if [[ ! -d ".git" ]]; then
        die "${INSTALL_DIR} is not a git repository. Cannot update without git."
    fi

    local current_branch
    current_branch=$(get_current_branch)

    # Determine the right remote to pull from
    local remote_name
    if git remote get-url "applone-fork" &>/dev/null 2>&1; then
        remote_name="applone-fork"
    elif git remote get-url "origin" &>/dev/null 2>&1; then
        remote_name="origin"
    else
        die "No git remote found to pull updates from."
    fi

    # Use --tag as the branch if it differs from current
    local target_branch="$IMAGE_TAG"
    if [[ "$current_branch" != "unknown" ]] && [[ "$target_branch" == "dev" ]]; then
        # Default tag "dev" – use the current branch if already on a fork branch
        target_branch="$current_branch"
    fi

    log_info "Remote: ${remote_name} | Branch: ${target_branch}"

    git fetch "$remote_name" "$target_branch" || die "Failed to fetch from ${remote_name}."

    local target_commit
    target_commit=$(git rev-parse --short "${remote_name}/${target_branch}" 2>/dev/null || \
                    git rev-parse --short "FETCH_HEAD")

    if [[ "$PRE_PATCH_COMMIT" == "$target_commit" ]]; then
        log_success "Already up-to-date (${target_commit}). Nothing to update."
        exit 0
    fi

    log_info "Current: ${PRE_PATCH_COMMIT} → Target: ${target_commit}"

    local stash_needed=false
    if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
        log_warn "Local modifications detected – stashing"
        git stash push -m "patch.sh update auto-stash $(date +%Y%m%d_%H%M%S)" --include-untracked
        stash_needed=true
    fi

    # Fast-forward merge if possible, otherwise reset
    if git merge --ff-only "${remote_name}/${target_branch}" 2>/dev/null; then
        log_success "Fast-forward merge to ${target_commit}"
    else
        log_warn "Cannot fast-forward; resetting branch to ${remote_name}/${target_branch}"
        git reset --hard "${remote_name}/${target_branch}"
        log_success "Reset to ${target_commit}"
    fi

    if $stash_needed; then
        git stash pop 2>/dev/null || \
            log_warn "Could not auto-apply stashed changes. Check 'git stash list'."
    fi

    bare_metal_post_update
}

# ══════════════════════════════════════════════════════════════════════
#  SHARED: bare-metal post-update steps
# ══════════════════════════════════════════════════════════════════════

bare_metal_post_update() {
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
    local banner_verb
    if [[ "$MODE" == "patch" ]]; then
        banner_verb="Patch"
    else
        banner_verb="Update"
    fi

    echo -e "\n${BOLD}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}║     PasarGuard Fork ${banner_verb} Script           ║${NC}"
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

    # Mode-specific validation
    if [[ "$MODE" == "update" ]]; then
        if ! is_fork_install; then
            die "This installation does not appear to be running the Applone fork.
    Use '${0} patch' first to switch from upstream to the fork."
        fi
    fi

    log_info "Mode:               ${MODE}"
    log_info "Install directory:  ${INSTALL_DIR}"
    log_info "Data directory:     ${DATA_DIR}"
    log_info "Deploy type:        ${DEPLOY_TYPE}"

    if [[ "$DEPLOY_TYPE" == "docker" ]]; then
        ORIGINAL_IMAGE=$(get_current_image)
        log_info "Current image:      ${ORIGINAL_IMAGE}"
        if [[ "$MODE" == "patch" ]]; then
            log_info "Target image:       ${FORK_IMAGE}:${IMAGE_TAG}"
        fi
    else
        PRE_PATCH_COMMIT=$(get_current_commit)
        local current_branch
        current_branch=$(get_current_branch)
        log_info "Current commit:     ${PRE_PATCH_COMMIT}"
        log_info "Current branch:     ${current_branch}"
        if [[ "$MODE" == "patch" ]]; then
            log_info "Target branch:      ${IMAGE_TAG}"
        fi
    fi

    if $DRY_RUN; then
        echo -e "\n${YELLOW}── DRY RUN MODE: No changes will be made ──${NC}\n"
    fi

    echo ""
    if [[ "$MODE" == "patch" ]]; then
        confirm "Patch this PasarGuard installation with the Applone fork?"
    else
        confirm "Update this PasarGuard fork installation to the latest version?"
    fi

    # ── Set rollback trap ────────────────────────────────────────────
    if ! $DRY_RUN; then
        trap 'rollback' ERR
    fi

    # ── Execute ──────────────────────────────────────────────────────
    create_backup
    stop_service

    if [[ "$MODE" == "patch" ]]; then
        if [[ "$DEPLOY_TYPE" == "docker" ]]; then
            patch_docker
        else
            patch_bare_metal
        fi
    else
        if [[ "$DEPLOY_TYPE" == "docker" ]]; then
            update_docker
        else
            update_bare_metal
        fi
    fi

    check_new_env_keys

    # Disable ERR trap before start (start failure ≠ rollback)
    trap - ERR

    start_service
    run_health_check

    # ── Summary ──────────────────────────────────────────────────────
    local done_label
    if [[ "$MODE" == "patch" ]]; then
        done_label="Patch applied successfully! ✓"
    else
        done_label="Update applied successfully! ✓"
    fi

    echo -e "\n${BOLD}${GREEN}╔══════════════════════════════════════════════╗${NC}"
    printf "${BOLD}${GREEN}║  %-43s ║${NC}\n" "$done_label"
    echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════╝${NC}\n"

    if [[ "$DEPLOY_TYPE" == "docker" ]]; then
        echo -e "  ${BOLD}Before:${NC}  ${ORIGINAL_IMAGE}"
        if [[ "$MODE" == "patch" ]]; then
            echo -e "  ${BOLD}After:${NC}   ${FORK_IMAGE}:${IMAGE_TAG}"
        else
            echo -e "  ${BOLD}After:${NC}   $(get_current_image) (latest digest)"
        fi
    else
        local new_commit
        new_commit=$(get_current_commit)
        echo -e "  ${BOLD}Before:${NC}  ${PRE_PATCH_COMMIT}"
        echo -e "  ${BOLD}After:${NC}   ${new_commit}"
        echo -e "  ${BOLD}Branch:${NC}  $(get_current_branch)"
    fi

    if [[ -n "$BACKUP_DIR" ]] && [[ -d "$BACKUP_DIR" ]]; then
        echo -e "  ${BOLD}Backup:${NC}  ${BACKUP_DIR}"
    fi

    echo -e "\n  To revert:"
    if [[ "$DEPLOY_TYPE" == "docker" ]]; then
        echo -e "    cp ${BACKUP_DIR}/app/docker-compose.yml ${COMPOSE_FILE}"
        echo -e "    docker compose -f ${COMPOSE_FILE} -p ${SERVICE_NAME} up -d"
    else
        echo -e "    cd ${INSTALL_DIR} && git checkout - && sudo systemctl restart ${SERVICE_NAME}"
    fi
    echo ""
}

main "$@"
