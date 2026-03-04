"""Community recipe & playbook sharing for zx — GitHub-based submission and discovery."""

import json
import re
import time
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Optional

from .config import CONFIG_DIR, ZxConfig

COMMUNITY_REPO = "aet-org/zx-community-recipes"
GITHUB_API = "https://api.github.com"
GITHUB_RAW = "https://raw.githubusercontent.com"

# GitHub OAuth App (public client ID — not a secret)
GITHUB_CLIENT_ID = "Ov23liBRPLEASEREPLACE"  # TODO: Replace with real OAuth App client ID
DEVICE_CODE_URL = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
OAUTH_SCOPES = "public_repo"

INDEX_CACHE_FILE = CONFIG_DIR / "community_index.json"
INDEX_CACHE_TTL = 3600  # 1 hour

COMMUNITY_DIR = CONFIG_DIR / "community"


# ── GitHub OAuth Device Flow ─────────────────────────────────────────────────


def _github_request(url: str, data: dict = None, token: str = "", method: str = "GET") -> dict:
    """Make a GitHub API request."""
    headers = {
        "Accept": "application/json",
        "User-Agent": "zx-cli",
    }
    if token:
        headers["Authorization"] = f"token {token}"

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
        if method == "GET":
            method = "POST"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API error {e.code}: {error_body}") from e


def _github_form_request(url: str, data: dict) -> dict:
    """Make a form-encoded POST request (for OAuth endpoints)."""
    headers = {
        "Accept": "application/json",
        "User-Agent": "zx-cli",
    }
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub OAuth error {e.code}: {error_body}") from e


def github_device_login() -> str:
    """Perform GitHub OAuth device flow login.

    Prints a code and URL for the user to authorize in their browser.
    Polls until authorized. Returns the access token.
    """
    from .ui import print_info, print_warning, print_success

    # Step 1: Request device code
    resp = _github_form_request(DEVICE_CODE_URL, {
        "client_id": GITHUB_CLIENT_ID,
        "scope": OAUTH_SCOPES,
    })

    device_code = resp["device_code"]
    user_code = resp["user_code"]
    verification_uri = resp["verification_uri"]
    interval = resp.get("interval", 5)
    expires_in = resp.get("expires_in", 900)

    print_info(f"\n  To authenticate with GitHub:")
    print_info(f"  1. Open: {verification_uri}")
    print_info(f"  2. Enter code: {user_code}")
    print_info(f"  Waiting for authorization...")

    # Step 2: Poll for access token
    deadline = time.time() + expires_in
    while time.time() < deadline:
        time.sleep(interval)
        try:
            token_resp = _github_form_request(ACCESS_TOKEN_URL, {
                "client_id": GITHUB_CLIENT_ID,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            })
        except Exception:
            continue

        if "access_token" in token_resp:
            print_success("GitHub authentication successful!")
            return token_resp["access_token"]

        error = token_resp.get("error", "")
        if error == "authorization_pending":
            continue
        elif error == "slow_down":
            interval += 5
            continue
        elif error == "expired_token":
            raise RuntimeError("Authorization expired. Please try again.")
        elif error == "access_denied":
            raise RuntimeError("Authorization denied by user.")
        else:
            raise RuntimeError(f"OAuth error: {error}")

    raise RuntimeError("Authorization timed out.")


def ensure_github_auth() -> str:
    """Check for saved GitHub token, prompt login if missing. Returns token."""
    config = ZxConfig.load()
    if config.github_token:
        # Validate token is still valid
        try:
            _github_request(f"{GITHUB_API}/user", token=config.github_token)
            return config.github_token
        except Exception:
            pass  # Token invalid, re-authenticate

    # Need to login
    token = github_device_login()
    config = ZxConfig.load()  # Reload in case of concurrent changes
    config.github_token = token
    config.save()
    return token


def get_github_username(token: str) -> str:
    """Get the authenticated GitHub username."""
    try:
        resp = _github_request(f"{GITHUB_API}/user", token=token)
        return resp.get("login", "anonymous")
    except Exception:
        return "anonymous"


def revoke_github_token() -> None:
    """Remove saved GitHub token from config."""
    config = ZxConfig.load()
    config.github_token = ""
    config.save()


# ── Submission ───────────────────────────────────────────────────────────────


def sanitize_for_sharing(data: dict) -> dict:
    """Strip personal/sensitive data before submission."""
    text = json.dumps(data)

    # Replace home directory paths
    home = str(Path.home())
    text = text.replace(home.replace("\\", "\\\\"), "~")
    text = text.replace(home.replace("\\", "/"), "~")
    text = text.replace(home, "~")

    # Remove potential API keys/tokens (common patterns)
    text = re.sub(r'(?i)(api[_-]?key|token|secret|password|passwd|credentials?)\s*[=:]\s*["\']?[\w\-\.]{8,}["\']?', r'\1=REDACTED', text)
    # Remove private IPs
    text = re.sub(r'\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})\b', 'REDACTED_IP', text)

    return json.loads(text)


def submit_recipe(recipe_data: dict, anonymous: bool = True) -> dict:
    """Submit a recipe to the community repo via GitHub Issue.

    Args:
        recipe_data: Recipe dict (from Recipe.to_dict())
        anonymous: If True, hide username from published recipe

    Returns:
        {"issue_url": ..., "status": "submitted"}
    """
    token = ensure_github_auth()
    username = get_github_username(token)

    # Sanitize
    clean = sanitize_for_sharing(recipe_data)
    clean["author"] = "anonymous" if anonymous else f"github:{username}"

    category = clean.get("tags", ["general"])[0] if clean.get("tags") else "general"
    title = f"[recipe] {category}/{clean.get('name', 'unnamed')}"

    labels = ["recipe-submission"]
    labels.append("anonymous" if anonymous else "identified")

    body = f"## Recipe Submission\n\n```json\n{json.dumps(clean, indent=2)}\n```"

    resp = _github_request(
        f"{GITHUB_API}/repos/{COMMUNITY_REPO}/issues",
        data={"title": title, "body": body, "labels": labels},
        token=token,
        method="POST",
    )

    return {"issue_url": resp.get("html_url", ""), "status": "submitted"}


def submit_playbook(playbook_data: dict, anonymous: bool = True) -> dict:
    """Submit a playbook to the community repo via GitHub Issue."""
    token = ensure_github_auth()
    username = get_github_username(token)

    clean = sanitize_for_sharing(playbook_data)
    clean["author"] = "anonymous" if anonymous else f"github:{username}"

    category = clean.get("category", "general")
    title = f"[playbook] {category}/{clean.get('name', 'unnamed')}"

    labels = ["playbook-submission"]
    labels.append("anonymous" if anonymous else "identified")

    body = f"## Playbook Submission\n\n```json\n{json.dumps(clean, indent=2)}\n```"

    resp = _github_request(
        f"{GITHUB_API}/repos/{COMMUNITY_REPO}/issues",
        data={"title": title, "body": body, "labels": labels},
        token=token,
        method="POST",
    )

    return {"issue_url": resp.get("html_url", ""), "status": "submitted"}


def report_success(item_type: str, item_name: str) -> None:
    """Report successful usage of a community recipe/playbook (opt-out).

    Creates a lightweight GitHub Issue for the Actions bot to increment counters.
    """
    config = ZxConfig.load()
    if config.community_opt_out or not config.github_token:
        return

    try:
        _github_request(
            f"{GITHUB_API}/repos/{COMMUNITY_REPO}/issues",
            data={
                "title": f"[success] {item_type}/{item_name}",
                "body": f"Automated success report for `{item_type}/{item_name}`.",
                "labels": ["success-report"],
            },
            token=config.github_token,
            method="POST",
        )
    except Exception:
        pass  # Silent failure — success reporting should never break the UX


# ── Browsing & Discovery ────────────────────────────────────────────────────


def fetch_community_index(force_refresh: bool = False) -> dict:
    """Fetch index.json from the community repo (cached locally).

    Returns:
        {"recipes": [...], "playbooks": [...], "last_updated": "..."}
    """
    # Check cache
    if not force_refresh and INDEX_CACHE_FILE.exists():
        try:
            cache = json.loads(INDEX_CACHE_FILE.read_text())
            cached_at = cache.get("_cached_at", 0)
            if time.time() - cached_at < INDEX_CACHE_TTL:
                return cache
        except (json.JSONDecodeError, TypeError):
            pass

    # Fetch from GitHub
    url = f"{GITHUB_RAW}/{COMMUNITY_REPO}/main/index.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "zx-cli"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            index = json.loads(resp.read().decode("utf-8"))
    except Exception:
        # Return cached version if available, even if stale
        if INDEX_CACHE_FILE.exists():
            try:
                return json.loads(INDEX_CACHE_FILE.read_text())
            except (json.JSONDecodeError, TypeError):
                pass
        return {"recipes": [], "playbooks": [], "last_updated": ""}

    # Save cache
    index["_cached_at"] = time.time()
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_CACHE_FILE.write_text(json.dumps(index, indent=2))

    return index


def search_community(query: str, item_type: str = "all") -> list[dict]:
    """Search community recipes/playbooks by keyword, tag, or category.

    Args:
        query: Search string
        item_type: "recipe", "playbook", or "all"

    Returns:
        List of matching items from the index
    """
    index = fetch_community_index()
    query_lower = query.lower()
    results = []

    sources = []
    if item_type in ("all", "recipe"):
        sources.extend([(r, "recipe") for r in index.get("recipes", [])])
    if item_type in ("all", "playbook"):
        sources.extend([(p, "playbook") for p in index.get("playbooks", [])])

    for item, itype in sources:
        searchable = " ".join([
            item.get("name", ""),
            item.get("description", ""),
            item.get("category", ""),
            " ".join(item.get("tags", [])),
            " ".join(item.get("symptoms", [])),
        ]).lower()

        if query_lower in searchable:
            item["_type"] = itype
            results.append(item)

    # Sort by success_count descending
    results.sort(key=lambda x: x.get("success_count", 0), reverse=True)
    return results


def download_community_item(item_type: str, category: str, name: str) -> Optional[dict]:
    """Download a specific recipe or playbook from the community repo.

    Args:
        item_type: "recipes" or "playbooks"
        category: Category directory (e.g., "python", "security")
        name: Item name (without .json)

    Returns:
        Parsed JSON dict or None
    """
    url = f"{GITHUB_RAW}/{COMMUNITY_REPO}/main/{item_type}/{category}/{name}.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "zx-cli"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def install_community_item(item_type: str, category: str, name: str) -> Optional[Path]:
    """Download and save a community item locally.

    Args:
        item_type: "recipes" or "playbooks"
        category: Category directory
        name: Item name

    Returns:
        Local file path or None
    """
    data = download_community_item(item_type, category, name)
    if not data:
        return None

    local_dir = COMMUNITY_DIR / item_type / category
    local_dir.mkdir(parents=True, exist_ok=True)

    safe_name = re.sub(r'[^\w\-]', '_', name)
    path = local_dir / f"{safe_name}.json"

    # Mark as community source
    data["source"] = "community"
    data["community_id"] = f"{category}/{name}"

    path.write_text(json.dumps(data, indent=2))
    return path


def match_playbooks_by_error(error_output: str) -> list[dict]:
    """Find community playbooks whose symptoms match an error.

    Args:
        error_output: The error text to match against

    Returns:
        List of matching playbooks sorted by success_count descending,
        each with a '_matched_symptoms' count field
    """
    index = fetch_community_index()
    playbooks = index.get("playbooks", [])
    error_lower = error_output.lower()

    matches = []
    for pb in playbooks:
        symptoms = pb.get("symptoms", [])
        matched = 0
        for symptom in symptoms:
            # Simple keyword matching — check if key phrases from the symptom appear in the error
            words = [w for w in symptom.lower().split() if len(w) > 3]
            if any(word in error_lower for word in words):
                matched += 1

        if matched > 0:
            pb["_matched_symptoms"] = matched
            pb["_total_symptoms"] = len(symptoms)
            matches.append(pb)

    # Sort: most matched symptoms first, then by success_count
    matches.sort(key=lambda x: (x["_matched_symptoms"], x.get("success_count", 0)), reverse=True)
    return matches


# ── Main Flows ───────────────────────────────────────────────────────────────


def run_explore(query: str = "") -> None:
    """Browse community recipes and playbooks."""
    from .ui import print_banner, print_info, print_warning, print_success, show_spinner

    print_banner()

    with show_spinner("thinking"):
        if query:
            results = search_community(query)
        else:
            index = fetch_community_index()
            results = []
            for r in index.get("recipes", []):
                r["_type"] = "recipe"
                results.append(r)
            for p in index.get("playbooks", []):
                p["_type"] = "playbook"
                results.append(p)

    if not results:
        if query:
            print_warning(f"No community items found for '{query}'.")
        else:
            print_warning("No community items available yet.")
        print_info("  Share your recipes with: zx recipe share <name>")
        return

    print_info(f"\n  Community {'search results' if query else 'catalog'}: {len(results)} items")
    print_info(f"  {'Type':<10} {'Name':<30} {'Uses':>5}  Description")
    print_info(f"  {'─'*10} {'─'*30} {'─'*5}  {'─'*40}")
    for item in results[:25]:
        itype = item.get("_type", "?")
        name = item.get("name", "unnamed")
        uses = item.get("success_count", 0)
        desc = item.get("description", "")[:40]
        print_info(f"  {itype:<10} {name:<30} {uses:>5}  {desc}")

    if len(results) > 25:
        print_info(f"  ... and {len(results) - 25} more. Use a search query to narrow results.")


def run_share(name: str, item_type: str = "recipe") -> None:
    """Share a local recipe or playbook to the community."""
    from .ui import print_banner, print_info, print_success, print_error, print_warning, show_spinner

    print_banner()

    # Load the item
    if item_type == "playbook":
        from .playbook import load_playbook
        item = load_playbook(name)
        if not item:
            print_error(f"Playbook '{name}' not found.")
            return
        data = item.to_dict()
    else:
        from .recipes import load_recipe
        item = load_recipe(name)
        if not item:
            print_error(f"Recipe '{name}' not found.")
            return
        data = item.to_dict()

    # Check eligibility
    if item.success_count < 3:
        print_warning(f"Recipe needs at least 3 successful runs to share (current: {item.success_count}).")
        print_info("  Run the recipe a few more times to build confidence before sharing.")
        return

    # Ask about anonymity
    try:
        anon_choice = input("  Share anonymously? [y/n] (default: y): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return
    anonymous = anon_choice != "n"

    print_info(f"  Sharing {item_type} '{name}' to community...")

    try:
        with show_spinner("thinking"):
            if item_type == "playbook":
                result = submit_playbook(data, anonymous=anonymous)
            else:
                result = submit_recipe(data, anonymous=anonymous)

        print_success(f"Submitted! Issue: {result['issue_url']}")
        print_info("  Your submission will be reviewed and added to the community catalog.")
    except Exception as e:
        print_error(f"Submission failed: {e}")


def run_install(item_path: str) -> None:
    """Install a community recipe or playbook locally.

    Args:
        item_path: "category/name" format (e.g., "python/flask-project")
    """
    from .ui import print_banner, print_info, print_success, print_error, show_spinner

    print_banner()

    parts = item_path.split("/", 1)
    if len(parts) != 2:
        print_error(f"Invalid format. Use: zx recipe install <category/name>")
        print_info("  Example: zx recipe install python/flask-project")
        return

    category, name = parts

    # Try recipes first, then playbooks
    for item_type in ("recipes", "playbooks"):
        with show_spinner("thinking"):
            path = install_community_item(item_type, category, name)
        if path:
            singular = "recipe" if item_type == "recipes" else "playbook"
            print_success(f"Installed {singular} '{name}' to {path}")
            return

    print_error(f"Could not find '{item_path}' in the community catalog.")
    print_info("  Use 'zx recipe explore' to browse available items.")
