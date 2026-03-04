"""URL-based installer for zx — fetches content from GitHub repos or any HTTPS URL,
analyzes it, and creates an installation plan."""

import re
from typing import Optional
from urllib.parse import urlparse

from .executor import execute_command


# ── URL classification ──────────────────────────────────────────────────────


def classify_url(url: str) -> Optional[str]:
    """Classify a URL as 'github', 'https', or None (invalid).

    Also accepts GitHub shorthand like 'owner/repo'.
    """
    # GitHub shorthand: owner/repo
    if re.match(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$", url):
        return "github"

    # Normalize
    normalized = url if "://" in url else f"https://{url}"
    parsed = urlparse(normalized)

    if not parsed.hostname:
        return None

    if "github.com" in parsed.hostname:
        return "github"

    if parsed.scheme in ("http", "https"):
        return "https"

    return None


# ── GitHub URL parsing ──────────────────────────────────────────────────────


def parse_github_url(url: str) -> Optional[tuple[str, str]]:
    """Extract (owner, repo) from a GitHub URL or shorthand.

    Supports:
        https://github.com/owner/repo
        https://github.com/owner/repo.git
        github.com/owner/repo
        owner/repo
    """
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]

    # Try full URL
    normalized = url if "://" in url else f"https://{url}"
    parsed = urlparse(normalized)
    if parsed.hostname and "github" in parsed.hostname:
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]

    # Try shorthand: owner/repo
    match = re.match(r"^([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)$", url)
    if match:
        return match.group(1), match.group(2)

    return None


# ── Content fetching ────────────────────────────────────────────────────────


def fetch_readme(owner: str, repo: str) -> Optional[str]:
    """Fetch README content from a GitHub repository.

    Tries gh CLI first (handles auth/private repos), falls back to curl.
    """
    # Try gh CLI
    result = execute_command(
        f'gh api repos/{owner}/{repo}/readme -q ".content" 2>/dev/null',
    )
    if result.success and result.stdout.strip():
        import base64
        try:
            return base64.b64decode(result.stdout.strip()).decode("utf-8")
        except Exception:
            pass

    # Fallback: raw URL for common README filenames
    for filename in ["README.md", "readme.md", "README.rst", "README.txt", "README"]:
        result = execute_command(
            f"curl -sL https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{filename}",
        )
        if result.success and result.stdout.strip() and "404" not in result.stdout[:20]:
            return result.stdout

    return None


def fetch_url_content(url: str) -> Optional[str]:
    """Fetch content from any HTTPS URL via curl.

    Strips HTML tags for readability. Truncates to 8000 chars.
    """
    normalized = url if "://" in url else f"https://{url}"
    result = execute_command(f'curl -sL "{normalized}"')

    if not result.success or not result.stdout.strip():
        return None

    content = result.stdout

    # Strip HTML tags if the response looks like HTML
    if "<html" in content.lower()[:500] or "<!doctype" in content.lower()[:500]:
        content = _strip_html(content)

    return content[:8000] if content.strip() else None


def _strip_html(html: str) -> str:
    """Lightweight HTML to text conversion."""
    # Remove script and style blocks
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Replace block elements with newlines
    html = re.sub(r"<(?:p|div|br|h[1-6]|li|tr)[^>]*>", "\n", html, flags=re.IGNORECASE)
    # Remove all remaining tags
    html = re.sub(r"<[^>]+>", "", html)
    # Decode common entities
    html = html.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    html = html.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # Collapse whitespace
    lines = [line.strip() for line in html.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines)


# ── Prompt building ─────────────────────────────────────────────────────────


def build_install_prompt(source_label: str, content: str) -> str:
    """Build the AI prompt for generating an installation plan from fetched content."""
    return f"""I want to install and set up software from: {source_label}

Here is the documentation/README content:
---
{content[:8000]}
---

Based on this content, create a complete installation plan:
1. Clone or download the project if needed
2. Check prerequisites (language runtimes, package managers, etc.)
3. Install all required dependencies
4. Run any setup, build, or configuration commands mentioned
5. Verify the installation works (run tests, check version, etc.)

If multiple installation methods are mentioned, prefer the simplest one.
If prerequisites are mentioned, include steps to check if they are installed.
If the content doesn't contain clear installation instructions, do your best to infer the steps."""
