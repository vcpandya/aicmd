"""Command safety analysis and risk scoring with pre-compiled patterns."""

import re

# Pre-compile all patterns at module load for performance

# Patterns that indicate destructive/dangerous commands
_DANGEROUS_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|--force|-[a-zA-Z]*f[a-zA-Z]*r)\b",
        r"\brm\s+(-[a-zA-Z]*f)\b.*[/\\]",
        r"\brm\s+-[a-zA-Z]*\s+[/~]",
        r"\bmkfs\b",
        r"\bformat\s+[a-zA-Z]:",
        r"\bdd\s+.*of=/dev/",
        r"\b>\s*/dev/sd",
        r"\bchmod\s+(-R\s+)?777\b",
        r"\bchown\s+-R\b.*[/\\]$",
        r"DROP\s+(TABLE|DATABASE|SCHEMA)",
        r"TRUNCATE\s+TABLE",
        r"DELETE\s+FROM\s+\S+\s*;?\s*$",
        r"\bgit\s+push\s+.*--force\b",
        r"\bgit\s+reset\s+--hard\b",
        r"\bgit\s+clean\s+-[a-zA-Z]*f",
        r":\(\)\{\s*:\|:&\s*\};:",  # Fork bomb (escaped for regex)
        r"\bshutdown\b",
        r"\breboot\b",
        r"\bhalt\b",
        r"\binit\s+0\b",
        r"\bkill\s+-9\s+-1\b",
        r"\bkillall\b",
        r"Remove-Item\s+.*-Recurse.*-Force",
        r"del\s+/[sS]\s+/[qQ]",
        r"rd\s+/[sS]\s+/[qQ]",
        r"\bcurl\b.*\|\s*(ba)?sh\b",  # curl pipe to shell
        r"\bwget\b.*\|\s*(ba)?sh\b",  # wget pipe to shell
    ]
]

# Patterns that indicate write/modify operations (moderate risk)
_MODERATE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\brm\b",
        r"\bmv\b",
        r"\bcp\b",
        r"\bmkdir\b",
        r"\bchmod\b",
        r"\bchown\b",
        r"\bgit\s+(commit|push|merge|rebase|checkout|branch\s+-[dD])\b",
        r"\bpip\s+install\b",
        r"\bnpm\s+install\b",
        r"\bapt(-get)?\s+install\b",
        r"\bbrew\s+install\b",
        r"\bdocker\s+(run|rm|stop|kill)\b",
        r"\bkubectl\s+(delete|apply|scale)\b",
        r"\bcurl\s+.*-X\s+(POST|PUT|DELETE|PATCH)\b",
        r"\bwget\b",
        r"\btee\b",
        r"\bsed\s+-i\b",
        r"[^-]>(?!>)",  # Output redirection (but not -gt or >>)
        r"\bsudo\b",
        r"Move-Item\b",
        r"Copy-Item\b",
        r"New-Item\b",
        r"Remove-Item\b",
        r"\bdel\b",
        r"\bmove\b",
        r"\bcopy\b",
        r"Set-Content\b",
        r"Add-Content\b",
        r"Out-File\b",
    ]
]

# Supersafe: trivial read-only commands that need zero confirmation
_SUPERSAFE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"^(ls|dir|ll)(\s+-[a-zA-Z]+)*\s*$",  # bare ls/dir with flags only
        r"^(ls|dir)\s+[\"']?[a-zA-Z0-9_./ \\~-]+[\"']?\s*$",  # ls <path>
        r"^(pwd|cd)\s*$",
        r"^(whoami|hostname|date|uname|uname\s+-[a-z]+)\s*$",
        r"^(echo|printf)\s+",
        r"^cat\s+",
        r"^(head|tail)\s+",
        r"^(wc|sort|uniq)\s+",
        r"^(python|node|ruby|go|cargo|java|rustc|gcc|make|dotnet)\s+--?(version|help)\s*$",
        r"^(pip|npm|yarn|cargo|gem|brew)\s+(list|show|search|info|freeze)\b",
        r"^git\s+(status|log|diff|show|branch|remote|tag)\b",
        r"^(systeminfo|ipconfig|ifconfig)\s*$",
        r"^ping\s+",
        r"^(Get-ChildItem|Get-Content|Get-Location|Get-Date|Get-Process|Get-Service|Get-Command|Get-Host)\b",
        r"^Write-Output\b",
        r"^(type|where|which)\s+",
        r"^(df|du|free|top|ps|env|set|printenv)\b",
        r"^tree(\s+-[a-zA-Z]+)*\s*$",
        r"^(curl|wget)\s+.*--?(help|version)\s*$",
    ]
]

# Read-only / safe commands (still needs confirmation but no danger)
_SAFE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"^(ls|dir|cat|type|head|tail|less|more|pwd|cd|echo|wc|sort|uniq|grep|find|which|where|whoami|hostname|date|time|df|du|free|top|ps|env|set|printenv|uname)\b",
        r"^git\s+(status|log|diff|show|branch|remote|stash\s+list|tag)\b",
        r"^(python|node|ruby|go|cargo|java|rustc|gcc|make)\s+--?(version|help)\b",
        r"^(pip|npm|yarn|cargo|gem|brew)\s+(list|show|search|info|freeze)\b",
        r"^docker\s+(ps|images|inspect|logs)\b",
        r"^kubectl\s+(get|describe|logs)\b",
        r"^Get-(ChildItem|Content|Location|Process|Service|Date|Host|Command)\b",
        r"^Write-Output\b",
        r"^Get-Date\b",
        r"^(systeminfo|ipconfig|ifconfig|ping|nslookup|tracert|traceroute|netstat)\b",
    ]
]


def analyze_risk(command: str) -> str:
    """
    Analyze a command and return risk level.
    Returns: 'SUPERSAFE', 'SAFE', 'MODERATE', or 'DANGEROUS'

    SUPERSAFE: trivial read-only commands — AI auto-executes with zero prompts.
    SAFE: read-only but may need user awareness.
    MODERATE: modifies files or state.
    DANGEROUS: destructive / irreversible — always requires manual confirmation.
    """
    cmd = command.strip()

    # Check dangerous first (highest priority)
    for pattern in _DANGEROUS_PATTERNS:
        if pattern.search(cmd):
            return "DANGEROUS"

    # Check supersafe (trivial read-only, zero friction)
    for pattern in _SUPERSAFE_PATTERNS:
        if pattern.search(cmd):
            return "SUPERSAFE"

    # Check safe patterns
    for pattern in _SAFE_PATTERNS:
        if pattern.search(cmd):
            return "SAFE"

    # Check moderate patterns
    for pattern in _MODERATE_PATTERNS:
        if pattern.search(cmd):
            return "MODERATE"

    # Default: moderate for unknown commands
    return "MODERATE"
