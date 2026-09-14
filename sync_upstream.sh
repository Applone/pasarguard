#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
#  sync_upstream.sh – Automatically merge updates from the upstream
#                     PasarGuard repository into this fork.
#
#  Upstream Repository: https://github.com/PasarGuard/panel.git
#  Fork Repository:     https://github.com/Applone/pasarguard.git
#
#  Usage:
#    bash sync_upstream.sh [COMMAND] [OPTIONS]
#
#  Commands:
#    merge                Fetch upstream and merge into current branch (default)
#    check                Check for new upstream commits/tags without merging
#    diff                 View incoming upstream commit log and diffstat
#    continue             Finalize merge after manually resolving conflicts
#    abort                Abort an in-progress merge and restore previous state
#
#  Options:
#    --ref <ref>          Upstream branch or tag to merge (default: upstream/main)
#    --tag <tag>          Merge a specific tag (e.g. v5.4.1)
#    --latest-tag         Automatically find and merge the latest upstream tag
#    --branch <branch>    Local branch to merge into (default: current branch)
#    --upstream-url <url> Upstream repository URL (default: PasarGuard/panel.git)
#    --push               Push to origin after a successful merge
#    --push-tags          Push upstream tags to origin
#    --dry-run            Simulate merge on a temporary branch without changes
#    --resolve-lockfiles  Auto-regenerate bun.lock / uv.lock on conflict
#    --skip-checks        Skip post-merge lint and dependency checks
#    --no-stash           Do not auto-stash uncommitted local changes
#    -y, --yes            Skip confirmation prompts
#    -h, --help           Show this help message
#
#  Examples:
#    bash sync_upstream.sh check                 # See what's new upstream
#    bash sync_upstream.sh                       # Merge upstream/main into current branch
#    bash sync_upstream.sh --tag v5.4.1          # Merge tag v5.4.1
#    bash sync_upstream.sh --latest-tag          # Merge latest release tag
#    bash sync_upstream.sh --dry-run             # Test if merge would have conflicts
#    bash sync_upstream.sh --push                # Merge and push to origin
#    bash sync_upstream.sh --abort               # Abort an in-progress merge
#    bash sync_upstream.sh --continue            # Finish merge after fixing conflicts
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Configuration Defaults ───────────────────────────────────────────
COMMAND="merge"
UPSTREAM_REPO_URL="https://github.com/PasarGuard/panel.git"
UPSTREAM_REMOTE="upstream"
ORIGIN_REMOTE="origin"
TARGET_REF=""
TARGET_BRANCH=""
USE_LATEST_TAG=false
SPECIFIED_TAG=""
AUTO_PUSH=false
PUSH_TAGS=false
DRY_RUN=false
AUTO_RESOLVE_LOCKFILES=false
SKIP_CHECKS=false
ALLOW_STASH=true
AUTO_YES=false

STATE_FILE=".git/sync_upstream_state"
BACKUP_REF_PREFIX="refs/backup/sync-upstream"

# ── Colors ───────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
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

# ── Argument Parsing ─────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        merge|check|diff|continue|abort)
            COMMAND="$1"
            shift
            ;;
        --ref)
            TARGET_REF="$2"
            shift 2
            ;;
        --tag)
            SPECIFIED_TAG="$2"
            shift 2
            ;;
        --latest-tag)
            USE_LATEST_TAG=true
            shift
            ;;
        --branch)
            TARGET_BRANCH="$2"
            shift 2
            ;;
        --upstream-url)
            UPSTREAM_REPO_URL="$2"
            shift 2
            ;;
        --push)
            AUTO_PUSH=true
            shift
            ;;
        --push-tags)
            PUSH_TAGS=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --resolve-lockfiles)
            AUTO_RESOLVE_LOCKFILES=true
            shift
            ;;
        --skip-checks)
            SKIP_CHECKS=true
            shift
            ;;
        --no-stash)
            ALLOW_STASH=false
            shift
            ;;
        -y|--yes)
            AUTO_YES=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            die "Unknown option or command: $1. Run with --help for options."
            ;;
    esac
done

# ── Helper Functions ─────────────────────────────────────────────────

confirm() {
    if $AUTO_YES; then return 0; fi
    local prompt="${1:-Proceed?}"
    echo -en "${BOLD}${prompt} [y/N]: ${NC}"
    read -r answer
    case "$answer" in
        [yY]|[yY][eE][sS]) return 0 ;;
        *) die "Aborted by user." ;;
    esac
}

require_git_repo() {
    if ! git rev-parse --is-inside-work-tree &>/dev/null; then
        die "Not inside a git repository."
    fi
}

ensure_upstream_remote() {
    if git remote get-url "$UPSTREAM_REMOTE" &>/dev/null; then
        local current_url
        current_url=$(git remote get-url "$UPSTREAM_REMOTE")
        if [[ "$current_url" != "$UPSTREAM_REPO_URL" ]]; then
            log_info "Updating remote '${UPSTREAM_REMOTE}' URL → ${UPSTREAM_REPO_URL}"
            git remote set-url "$UPSTREAM_REMOTE" "$UPSTREAM_REPO_URL"
        fi
    else
        log_info "Adding remote '${UPSTREAM_REMOTE}' → ${UPSTREAM_REPO_URL}"
        git remote add "$UPSTREAM_REMOTE" "$UPSTREAM_REPO_URL"
    fi
}

fetch_upstream() {
    log_info "Fetching latest commits and tags from '${UPSTREAM_REMOTE}'..."
    git fetch "$UPSTREAM_REMOTE" --tags --prune
}

get_latest_upstream_tag() {
    git tag -l "v*" --sort=-v:refname | head -n 1 || true
}

determine_target_ref() {
    if [[ -n "$SPECIFIED_TAG" ]]; then
        TARGET_REF="tags/${SPECIFIED_TAG}"
    elif $USE_LATEST_TAG; then
        local tag
        tag=$(get_latest_upstream_tag)
        if [[ -z "$tag" ]]; then
            die "No version tags (v*) found from upstream."
        fi
        TARGET_REF="tags/${tag}"
        log_info "Detected latest upstream tag: ${tag}"
    elif [[ -z "$TARGET_REF" ]]; then
        # Check if upstream/main exists, otherwise fallback to upstream/dev or HEAD
        if git rev-parse --verify "${UPSTREAM_REMOTE}/main" &>/dev/null; then
            TARGET_REF="${UPSTREAM_REMOTE}/main"
        elif git rev-parse --verify "${UPSTREAM_REMOTE}/dev" &>/dev/null; then
            TARGET_REF="${UPSTREAM_REMOTE}/dev"
        else
            TARGET_REF="${UPSTREAM_REMOTE}/HEAD"
        fi
    fi
}

# ── Subcommand: ABORT ────────────────────────────────────────────────

cmd_abort() {
    log_step "Aborting in-progress merge"
    require_git_repo

    if [[ ! -f .git/MERGE_HEAD ]]; then
        log_warn "No merge is currently in progress."
        if [[ -f "$STATE_FILE" ]]; then
            rm -f "$STATE_FILE"
            log_info "Cleared leftover sync state."
        fi
        exit 0
    fi

    git merge --abort
    log_success "Merge aborted. Working tree restored."

    if [[ -f "$STATE_FILE" ]]; then
        # shellcheck source=/dev/null
        source "$STATE_FILE" 2>/dev/null || true
        if [[ -n "${STASH_HASH:-}" ]]; then
            log_info "Restoring auto-stashed changes (${STASH_HASH})..."
            git stash pop 2>/dev/null || log_warn "Could not cleanly auto-pop stash. Check 'git stash list'."
        fi
        rm -f "$STATE_FILE"
    fi
}

# ── Subcommand: CONTINUE ─────────────────────────────────────────────

cmd_continue() {
    log_step "Continuing merge after conflict resolution"
    require_git_repo

    if [[ ! -f .git/MERGE_HEAD ]]; then
        die "No merge in progress to continue. Use 'sync_upstream.sh merge' to start a new merge."
    fi

    # Check for remaining conflicts
    local conflicts
    conflicts=$(git diff --name-only --diff-filter=U)
    if [[ -n "$conflicts" ]]; then
        log_error "There are still unresolved merge conflicts in:"
        echo "$conflicts" | sed 's/^/  - /'
        echo ""
        log_warn "Please resolve all conflict markers, stage them with 'git add <file>', and run again."
        exit 1
    fi

    # Load saved state if exists
    local target_ref_name="upstream"
    local stash_hash=""
    if [[ -f "$STATE_FILE" ]]; then
        # shellcheck source=/dev/null
        source "$STATE_FILE" 2>/dev/null || true
        target_ref_name="${STATE_TARGET_REF:-$target_ref_name}"
        stash_hash="${STASH_HASH:-}"
    fi

    log_info "All conflicts resolved. Finalizing commit..."
    git commit --no-edit

    log_success "Merge committed successfully!"

    if [[ -n "$stash_hash" ]]; then
        log_info "Restoring auto-stashed local modifications..."
        git stash pop 2>/dev/null || log_warn "Could not cleanly auto-pop stash. Check 'git stash list'."
    fi

    rm -f "$STATE_FILE"

    run_post_merge_steps
}

# ── Subcommand: CHECK ────────────────────────────────────────────────

cmd_check() {
    log_step "Checking upstream repository status"
    require_git_repo
    ensure_upstream_remote
    fetch_upstream
    determine_target_ref

    local current_branch
    current_branch=$(git branch --show-current)
    local current_commit
    current_commit=$(git rev-parse --short HEAD)
    local target_commit
    target_commit=$(git rev-parse --short "$TARGET_REF")
    local latest_tag
    latest_tag=$(get_latest_upstream_tag)

    echo -e "\n${BOLD}Status Summary:${NC}"
    echo -e "  Local Branch:      ${CYAN}${current_branch}${NC} (${current_commit})"
    echo -e "  Upstream Ref:      ${CYAN}${TARGET_REF}${NC} (${target_commit})"
    echo -e "  Latest Tag:        ${GREEN}${latest_tag:-None}${NC}"

    local behind_count ahead_count
    behind_count=$(git rev-list --count "HEAD..${TARGET_REF}" 2>/dev/null || echo "0")
    ahead_count=$(git rev-list --count "${TARGET_REF}..HEAD" 2>/dev/null || echo "0")

    echo -e "  Commits Behind:    ${YELLOW}${behind_count}${NC}"
    echo -e "  Fork Commits Ahead:${MAGENTA}${ahead_count}${NC}\n"

    if [[ "$behind_count" -eq 0 ]]; then
        log_success "Your branch is up to date with ${TARGET_REF}! No merge needed."
        return 0
    fi

    log_info "Incoming upstream commits (${behind_count}):"
    git log -n 15 --oneline "HEAD..${TARGET_REF}" | sed 's/^/  /'
    if [[ "$behind_count" -gt 15 ]]; then
        echo -e "  ... and $((behind_count - 15)) more commits."
    fi

    echo ""
    log_info "Run '${0} merge' to merge these updates."
}

# ── Subcommand: DIFF ─────────────────────────────────────────────────

cmd_diff() {
    log_step "Comparing current branch with upstream"
    require_git_repo
    ensure_upstream_remote
    fetch_upstream
    determine_target_ref

    log_info "Changes between HEAD and ${TARGET_REF}:"
    git diff --stat "HEAD...${TARGET_REF}"
}

# ── Automatic Lockfile Conflict Resolver ─────────────────────────────

auto_resolve_lockfiles() {
    local conflicts
    conflicts=$(git diff --name-only --diff-filter=U)

    # Handle dashboard/bun.lock
    if echo "$conflicts" | grep -q "dashboard/bun.lock"; then
        log_step "Auto-resolving conflict in dashboard/bun.lock"
        if command -v bun &>/dev/null; then
            log_info "Re-generating bun.lock using local bun..."
            # Accept upstream package.json or merged package.json, then rebuild lock
            (cd dashboard && bun install)
            git add dashboard/bun.lock
            log_success "dashboard/bun.lock regenerated and staged"
        else
            log_warn "bun not installed. Cannot auto-regenerate dashboard/bun.lock."
        fi
    fi

    # Handle uv.lock
    if echo "$conflicts" | grep -q "uv.lock"; then
        log_step "Auto-resolving conflict in uv.lock"
        if command -v uv &>/dev/null; then
            log_info "Re-generating uv.lock using local uv..."
            uv lock || uv sync
            git add uv.lock
            log_success "uv.lock regenerated and staged"
        else
            log_warn "uv not installed. Cannot auto-regenerate uv.lock."
        fi
    fi
}

# ── Post-Merge Validation and Push ───────────────────────────────────

run_post_merge_steps() {
    if ! $SKIP_CHECKS; then
        log_step "Post-merge verification"

        # Check Python dependencies
        if command -v uv &>/dev/null; then
            log_info "Verifying Python dependencies with uv sync..."
            if uv sync --frozen 2>/dev/null || uv sync; then
                log_success "Python dependencies verified"
            else
                log_warn "uv sync failed. Check pyproject.toml."
            fi
        fi

        # Check frontend dependencies
        if command -v bun &>/dev/null && [[ -d "dashboard" ]]; then
            log_info "Verifying frontend dependencies with bun install..."
            if (cd dashboard && bun install); then
                log_success "Frontend dependencies verified"
            else
                log_warn "bun install failed. Check dashboard/package.json."
            fi
        fi

        # Check Alembic migrations
        if command -v uv &>/dev/null && [[ -f "alembic.ini" ]]; then
            log_info "Checking database migrations consistency..."
            if uv run alembic check 2>/dev/null; then
                log_success "Alembic migrations are consistent"
            else
                log_info "Alembic check completed."
            fi
        fi
    fi

    # Push to origin if requested
    if $AUTO_PUSH; then
        local current_branch
        current_branch=$(git branch --show-current)
        log_step "Pushing merged changes to '${ORIGIN_REMOTE}/${current_branch}'"
        git push "$ORIGIN_REMOTE" "$current_branch"
        log_success "Pushed ${current_branch} to ${ORIGIN_REMOTE}"

        if $PUSH_TAGS; then
            log_info "Pushing tags to ${ORIGIN_REMOTE}..."
            git push "$ORIGIN_REMOTE" --tags
            log_success "Tags pushed to ${ORIGIN_REMOTE}"
        fi
    else
        echo ""
        log_info "Merge is local. Push to GitHub when ready with:"
        echo -e "    ${BOLD}git push ${ORIGIN_REMOTE} $(git branch --show-current)${NC}"
        if $PUSH_TAGS; then
            echo -e "    ${BOLD}git push ${ORIGIN_REMOTE} --tags${NC}"
        fi
    fi
}

# ── Subcommand: MERGE ────────────────────────────────────────────────

cmd_merge() {
    require_git_repo

    if [[ -f .git/MERGE_HEAD ]]; then
        die "A merge is already in progress!
    To finish: resolve conflicts and run '${0} continue'
    To cancel: run '${0} abort'"
    fi

    ensure_upstream_remote
    fetch_upstream
    determine_target_ref

    # Determine branches
    local current_branch
    current_branch=$(git branch --show-current)

    if [[ -n "$TARGET_BRANCH" && "$TARGET_BRANCH" != "$current_branch" ]]; then
        log_info "Switching to branch '${TARGET_BRANCH}'..."
        git checkout "$TARGET_BRANCH"
        current_branch="$TARGET_BRANCH"
    fi

    local current_commit
    current_commit=$(git rev-parse --short HEAD)
    local target_commit
    target_commit=$(git rev-parse --short "$TARGET_REF")

    log_step "Preparing merge"
    echo -e "  Branch:        ${BOLD}${CYAN}${current_branch}${NC} (${current_commit})"
    echo -e "  Upstream Ref:  ${BOLD}${MAGENTA}${TARGET_REF}${NC} (${target_commit})"

    # Check if up to date
    local behind_count
    behind_count=$(git rev-list --count "HEAD..${TARGET_REF}" 2>/dev/null || echo "0")
    if [[ "$behind_count" -eq 0 ]]; then
        log_success "Already up-to-date with ${TARGET_REF}. Nothing to merge!"
        exit 0
    fi

    echo -e "  New commits:   ${YELLOW}${behind_count}${NC}"
    echo ""
    git log -n 10 --oneline "HEAD..${TARGET_REF}" | sed 's/^/    /'
    if [[ "$behind_count" -gt 10 ]]; then
        echo "    ... and $((behind_count - 10)) more"
    fi
    echo ""

    # Dry run simulation
    if $DRY_RUN; then
        log_step "Simulating merge on an ephemeral temporary branch"
        local dry_branch="__dryrun_sync_$(date +%s)"
        git checkout -b "$dry_branch" HEAD --quiet
        local dry_status=0
        if git merge --no-commit --no-ff "$TARGET_REF" &>/dev/null; then
            log_success "Dry-run: Merge would apply CLEANLY with no conflicts! ✓"
            git merge --abort &>/dev/null || true
        else
            log_warn "Dry-run: Merge would encounter conflicts in:"
            git diff --name-only --diff-filter=U | sed 's/^/  - /'
            git merge --abort &>/dev/null || true
            dry_status=1
        fi
        git checkout "$current_branch" --quiet
        git branch -D "$dry_branch" --quiet
        exit $dry_status
    fi

    confirm "Merge '${TARGET_REF}' into '${current_branch}'?"

    # Working tree safety: stash if dirty
    local stash_hash=""
    if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
        if $ALLOW_STASH; then
            log_warn "Working directory has uncommitted changes. Auto-stashing..."
            git stash push -m "sync_upstream auto-stash $(date +%Y%m%d_%H%M%S)" --include-untracked
            stash_hash=$(git rev-parse -q --verify refs/stash || true)
            log_info "Changes stashed (${stash_hash})"
        else
            die "Working directory is not clean. Commit or stash your changes first."
        fi
    fi

    # Create safety backup ref before merge
    local timestamp
    timestamp="$(date +%Y%m%d_%H%M%S)"
    local backup_ref="${BACKUP_REF_PREFIX}-${timestamp}"
    git update-ref "$backup_ref" HEAD
    log_info "Safety backup created at: ${backup_ref}"

    # Save state for abort/continue
    cat > "$STATE_FILE" <<EOF
STATE_TARGET_REF="${TARGET_REF}"
STATE_BRANCH="${current_branch}"
BACKUP_REF="${backup_ref}"
STASH_HASH="${stash_hash}"
EOF

    # Execute merge
    log_step "Executing git merge"
    local merge_msg="Merge upstream ref '${TARGET_REF}' into ${current_branch}"

    if git merge --no-edit -m "$merge_msg" "$TARGET_REF"; then
        log_success "Merge completed cleanly! ✓"
        rm -f "$STATE_FILE"

        if [[ -n "$stash_hash" ]]; then
            log_info "Restoring auto-stashed changes..."
            git stash pop 2>/dev/null || log_warn "Could not cleanly auto-pop stash. Check 'git stash list'."
        fi

        run_post_merge_steps
    else
        log_error "Merge encountered conflicts!"

        # Check if lockfiles can be auto-resolved
        if $AUTO_RESOLVE_LOCKFILES; then
            auto_resolve_lockfiles
        fi

        local remaining_conflicts
        remaining_conflicts=$(git diff --name-only --diff-filter=U)

        if [[ -z "$remaining_conflicts" ]]; then
            log_success "All conflicts were auto-resolved lockfiles! Finalizing commit..."
            git commit --no-edit
            rm -f "$STATE_FILE"
            run_post_merge_steps
            exit 0
        fi

        echo -e "\n${BOLD}Conflicting files:${NC}"
        echo "$remaining_conflicts" | sed -e "s/^/  ${RED}✖${NC} /"

        echo -e "\n${BOLD}${YELLOW}Next Steps:${NC}"
        echo -e "  1. Open the conflicting files above and resolve conflict markers (${CYAN}<<<<<<<${NC}, ${CYAN}=======${NC}, ${CYAN}>>>>>>>${NC})"
        echo -e "  2. Mark resolved files with:   ${BOLD}git add <file>${NC}"
        echo -e "  3. Finish the merge with:      ${BOLD}bash ${0} continue${NC}"
        echo -e "     (or cancel anytime with:    ${BOLD}bash ${0} abort${NC})"
        echo ""
        echo -e "  To completely reset to pre-merge state:"
        echo -e "    ${BOLD}git merge --abort && git reset --hard ${backup_ref}${NC}\n"
        exit 1
    fi
}

# ══════════════════════════════════════════════════════════════════════
#  MAIN ENTRYPOINT
# ══════════════════════════════════════════════════════════════════════

main() {
    echo -e "\n${BOLD}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}║     PasarGuard Upstream Sync Tool            ║${NC}"
    echo -e "${BOLD}║     Upstream: PasarGuard/panel               ║${NC}"
    echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}\n"

    case "$COMMAND" in
        merge)    cmd_merge ;;
        check)    cmd_check ;;
        diff)     cmd_diff ;;
        continue) cmd_continue ;;
        abort)    cmd_abort ;;
        *)        die "Unknown command: ${COMMAND}" ;;
    esac
}

main "$@"
