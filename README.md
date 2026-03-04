<p align="center">
  <pre>
     ____  __
    |_  / / /
     / / / /_
    /___/\__/
  </pre>
</p>

<h1 align="center">zx — Speak Human, Run Machine</h1>

<p align="center">
  Natural language to terminal commands, powered by AI.<br>
  Type what you want in plain English. Get the exact terminal command.<br>
  Supports <strong>100+ AI providers</strong> — Gemini, OpenRouter, Ollama, vLLM, and more via LiteLLM.<br>
  Works on <strong>Windows</strong> (cmd / PowerShell), <strong>Linux</strong>, and <strong>macOS</strong>.
</p>

<p align="center">
  <a href="#installation">Install</a> &bull;
  <a href="#quick-start">Quick Start</a> &bull;
  <a href="#features">Features</a> &bull;
  <a href="#multi-provider-support">Providers</a> &bull;
  <a href="#cost-tracking--budgets">Cost Tracking</a> &bull;
  <a href="#command-reference">Commands</a> &bull;
  <a href="#configuration">Config</a>
</p>

---

## Installation

**Requirements:** Python 3.10+

```bash
pip install zx-ai
```

For Gemini fallback support (optional):
```bash
pip install zx-ai[gemini]
```

Then run the setup wizard:

```bash
zx setup
```

This will prompt you to select your AI provider(s), enter API keys, choose a default model, and configure budget limits.

> **Tip:** You can also set provider-specific environment variables (e.g., `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`) instead of running setup.

---

## Quick Start

```bash
# Natural language — just say what you want
zx "list all python files in this directory"
zx "find files larger than 100MB"
zx "create a virtual environment and install flask"

# Multi-step plans — AI builds and executes a full plan
zx "set up a new React project with TypeScript and Tailwind CSS"

# Explain unfamiliar commands
zx explain "tar -xzf archive.tar.gz"

# Fix errors instantly
npm run build 2>&1 | zx fix

# Learn shell skills interactively
zx learn

# Track your AI spending
zx cost
```

---

## Multi-Provider Support

zx uses **LiteLLM** as its AI backend, giving you access to 100+ providers with a unified interface. Switch providers by changing your model string — no code changes needed.

### Supported Providers

| Provider | Model Format | API Key Env Var |
|----------|-------------|-----------------|
| **Google Gemini** | `gemini/gemini-2.0-flash-lite` | `GEMINI_API_KEY` |
| **OpenRouter** | `openrouter/anthropic/claude-3.5-sonnet` | `OPENROUTER_API_KEY` |
| **OpenAI** | `openai/gpt-4o` | `OPENAI_API_KEY` |
| **Anthropic** | `anthropic/claude-3.5-sonnet` | `ANTHROPIC_API_KEY` |
| **Ollama** (local) | `ollama_chat/gemma3` | None (free) |
| **vLLM** (local) | `vllm/my-model` | None (free) |
| **Any LiteLLM provider** | See [LiteLLM docs](https://docs.litellm.ai/docs/providers) | Varies |

### Using Local Models (Free & Private)

Run entirely offline with Ollama or vLLM — no API key needed, no data leaves your machine, and local models always bypass budget limits.

```bash
# Install Ollama (https://ollama.com)
ollama pull gemma3

# Configure zx to use it
zx setup
# > Select provider: Ollama
# > Model: ollama_chat/gemma3
```

### Using Cloud Providers

```bash
# Set API key via environment variable
export OPENROUTER_API_KEY="sk-or-..."

# Or configure via setup wizard
zx setup
# > Select provider: OpenRouter
# > API key: sk-or-...
# > Model: openrouter/anthropic/claude-3.5-sonnet
```

---

## Cost Tracking & Budgets

zx tracks every AI call — tokens used, estimated cost, and which model was called. Usage is persisted to `~/.zx/usage.json` with per-model and daily breakdowns.

### View Costs

```bash
# Show monthly summary with per-model and daily breakdown
zx cost

# Show a specific month
zx cost 2026-03

# Clear usage data for a month
zx cost --reset
```

Example output:
```
March 2026: $1.2340 / $5.00 budget | 45,678 tokens | 89 calls

Per-model breakdown:
  gemini/gemini-2.0-flash-lite: $0.8012 | 30,000 tokens | 60 calls
  openrouter/anthropic/claude-3.5-sonnet: $0.4328 | 15,678 tokens | 29 calls

Recent daily usage:
  2026-03-05: $0.1200 | 5,000 tokens | 10 calls
  2026-03-04: $0.0800 | 3,200 tokens | 8 calls
```

### Set Budget Limits

```bash
# Set monthly spending limit
zx budget --monthly 5.00

# Set per-session limit
zx budget --session 0.50

# View current budget settings
zx budget --show

# Remove limits (set to 0)
zx budget --monthly 0
```

**Budget behavior:**
- Cloud providers are blocked when over budget
- Local models (Ollama, vLLM) always bypass budget checks
- Cost summary shown after every AI-powered command (configurable)

---

## Features

### Plan-then-Execute (Default Mode)

When you give zx a task, it generates a **complete execution plan** upfront — with risk assessment, reversibility info, and step-by-step explanations. You review everything before a single command runs.

```bash
zx "set up a python project with venv, install flask, and create a hello world app"
```

The plan shows a table with:
- Each command and what it does
- Risk level: **SUPERSAFE** / **SAFE** / **MODERATE** / **DANGEROUS**
- Whether each step can be undone
- Warnings and caveats

After approval, zx executes step by step. If a step fails, the AI **adapts the plan** automatically — diagnosing the issue and revising remaining steps.

---

### Safety Analysis

Every command is scored for risk before execution:

| Level | Color | Behavior | Example |
|-------|-------|----------|---------|
| **SUPERSAFE** | Green | Auto-executes silently | `ls`, `pwd`, `git status` |
| **SAFE** | Green | Shown but low-risk | `cat`, `head`, `pip list` |
| **MODERATE** | Yellow | Requires confirmation | `mkdir`, `pip install`, `git commit` |
| **DANGEROUS** | Red | Always requires manual confirmation | `rm -rf`, `git push --force`, `DROP TABLE` |

Auto-approve (`--yes`) never bypasses DANGEROUS commands.

---

### Workflow Recipes

Save successful plans as reusable recipes with parameter support.

```bash
# After a plan completes, you're offered to save it as a recipe
# Or save the last plan manually:
zx recipe --save flask-project

# List saved recipes
zx recipe --list

# Replay a recipe with parameters
zx recipe flask-project
# > Enter value for 'project_name': myapp

# Export / Import for sharing
zx recipe --export flask-project    # Creates flask-project.zxrecipe
zx recipe --import setup.zxrecipe   # Imports a shared recipe

# Delete a recipe
zx recipe --delete old-recipe
```

Recipes support **template parameters** — when you save a recipe, AI analyzes the commands and identifies which parts should become `{{parameters}}` (project names, versions, paths) so the recipe works in different contexts.

---

### Time-Travel Undo

Reverse the last executed plan.

```bash
# Undo the entire last plan (in reverse order)
zx undo

# Undo only the last 3 steps
zx undo --steps 3

# Preview what would be undone (no execution)
zx undo --dry-run
```

zx uses the undo commands from the plan (if the AI marked steps as reversible). For steps without undo info, it asks the AI to generate a reversal command on the fly.

---

### Failure Doctor

Diagnose and fix command failures instantly.

```bash
# Pipe error output directly
npm run build 2>&1 | zx fix

# Describe the error manually
zx fix "pip install numpy failed with compilation error"

# Auto-read the last failed command from shell history
zx fix
```

The doctor provides:
- **Root cause** — plain-English explanation
- **Fix command** — ready to execute (with risk analysis)
- **Prevention tip** — how to avoid this in the future
- **Confidence level** — high / medium / low

---

### Smart Alias Generator

Analyze your command history and generate shell aliases.

```bash
# AI-powered suggestions based on your usage patterns
zx alias suggest

# Create an alias from natural language
zx alias "deploy to production"

# Manually add an alias
zx alias add --name gs --command "git status"

# List saved aliases
zx alias list

# Install aliases to your shell profile (~/.bashrc, ~/.zshrc, PowerShell profile)
zx alias install
```

Generates correct syntax for bash, zsh, fish, PowerShell, and cmd.

---

### Context Snapshots

Record and compare system state before and after changes.

```bash
# Take a snapshot
zx snapshot take my-baseline

# List saved snapshots
zx snapshot list

# Compare current state vs a snapshot
zx snapshot diff my-baseline

# Show snapshot details
zx snapshot show my-baseline

# Auto before/after snapshots during execution
zx "install project dependencies" --snapshot

# Delete a snapshot
zx snapshot delete my-baseline
```

Snapshots capture: file tree, git status/branch/commit, environment variables, installed packages, and disk space.

---

### Shell Tutor

Interactive learning mode with 25 topics across 5 categories.

```bash
# Start learning (suggests next topic based on your progress)
zx learn

# Learn a specific topic
zx learn "git basics"
zx learn pipes

# View your skill tree and progress
zx learn --progress
```

**Categories:**
- **Shell Basics** — navigation, file operations, permissions, help system
- **Text Processing** — grep, sed/awk, pipes, redirection
- **System Administration** — processes, disk, networking, services
- **Development Tools** — git, package managers, containers, debugging
- **Scripting** — variables, conditionals, loops, functions, error handling

Lessons adapt to what you've already mastered. Your progress is tracked in `~/.zx/learner_profile.json`.

---

### Live Narration

Execute commands with real-time AI commentary.

```bash
zx narrate "npm install"
zx narrate "docker build -t myapp ."
zx narrate "python manage.py migrate"
```

As the command runs, the AI watches the output stream and provides commentary:
- Flags errors and warnings immediately
- Explains what's happening during long builds
- Highlights unexpected patterns

---

### Remote Execution

Run commands on remote hosts via SSH.

```bash
# Add remote hosts
zx remote add dev user@192.168.1.100
zx remote add staging deploy@staging.example.com

# List configured remotes
zx remote list

# Execute on a specific host using natural language
zx @dev "check disk space and running containers"
zx @staging "restart nginx"

# Fan-out to ALL configured hosts
zx @all "check system uptime"

# Remove a remote
zx remote remove old-server
```

zx detects the remote environment (OS, shell) before generating commands, so it produces the right syntax for each host.

---

### Incident Playbooks

Playbooks are incident-response recipes — they capture symptoms, diagnostic steps, fixes, and prevention tips for common problems.

```bash
# List all playbooks (local + community)
zx playbook list

# Run a playbook by name
zx playbook fix-npm-supply-chain

# Create a playbook from a fix session
# (Automatically offered after 'zx fix' succeeds)
zx fix "npm install fails with ERESOLVE"
# > Fix applied! Save as reusable playbook? [y/n]

# Share a playbook with the community
zx playbook share --name fix-npm-supply-chain
```

Playbooks include:
- **Symptoms** — observable signs that help match errors automatically
- **Diagnostic steps** — safe read-only commands to confirm the issue
- **Fix steps** — the actual remediation commands (with risk analysis)
- **Prevention tips** — how to avoid this in the future
- **Severity level** — critical / high / medium / low

When you run `zx fix`, it checks community playbooks first — if someone else already solved your exact problem, you get an instant fix.

---

### Community Sharing

Share your recipes and playbooks with the zx community.

```bash
# Browse community recipes and playbooks
zx recipe explore
zx recipe explore "flask"

# Install a community recipe locally
zx recipe --install python/flask-project

# Share a recipe (requires 3+ successful runs)
zx recipe --share flask-project

# Share a playbook
zx playbook share --name fix-npm-supply-chain
```

**How it works:**
1. Sign in with GitHub (device flow — like `gh auth login`)
2. Your recipe/playbook is submitted as a GitHub Issue to the community repo
3. Automated validation checks format, scans for secrets, and flags issues
4. Trusted contributors get auto-merged; new submissions go through review
5. Approved items appear in `zx recipe explore` for everyone

**Privacy:**
- Choose to share anonymously or with your GitHub username
- Personal paths, API keys, and private IPs are automatically stripped
- Success reporting is opt-out (configured in `zx setup`)

**Quality:**
- Only recipes with 3+ successful runs are eligible for sharing
- Community items show their success count so you can judge reliability

---

### Install from URL

Point at any GitHub repo or documentation page and zx creates an installation plan.

```bash
zx install pallets/flask              # GitHub shorthand
zx install https://github.com/user/repo
zx install https://docs.example.com/setup-guide
```

Fetches the README / page content, generates a step-by-step installation plan, and executes with mandatory approval per step.

---

### Explain Mode

Learn what unfamiliar commands do.

```bash
zx explain "tar -xzf archive.tar.gz"
zx explain "awk '{print $2}' file.txt"
zx explain "find . -name '*.log' -mtime +30 -delete"
```

Shows a breakdown of each flag and argument, plus any risks or side effects.

---

### Pipe Support

Combine with existing tools:

```bash
cat error.log | zx "find the most common error"
docker logs app | zx "summarize what went wrong"
git diff | zx "explain these changes"
```

---

### Clean / Classic Mode

Strip away all colors, panels, emojis, and witty messages for a plain-text experience. Ideal for CI/CD pipelines, screen readers, or minimal terminals.

**Three ways to activate:**

```bash
# Per-command
zx --clean "list files"

# Environment variable (great for CI/CD)
ZX_CLEAN=1 zx "run tests"

# Persistent (via setup wizard)
zx setup
# > Enable clean/classic mode? Yes
```

---

## Command Reference

```
zx "prompt"                          Plan mode (default)
zx "prompt" --yes / -y               Auto-approve (except dangerous)
zx "prompt" --single / -s            Single command only
zx "prompt" --no-plan                Legacy multi-step mode
zx "prompt" --copy / -c              Copy to clipboard
zx "prompt" --snapshot               Auto before/after snapshots
zx --clean "prompt"                  Plain text mode

zx setup                             Configure providers, models, and budgets
zx explain "command"                 Explain a command
zx history [--clear]                 Browse or clear history
zx last                              Show last command
zx install <url>                     Install from URL

zx cost [month]                      Show AI usage costs and breakdown
zx cost --reset                      Clear usage data for a month
zx budget --monthly <amount>         Set monthly spending limit
zx budget --session <amount>         Set per-session spending limit
zx budget --show                     Show current budget settings

zx recipe --list                     List saved recipes
zx recipe <name>                     Replay a recipe
zx recipe --save <name>              Save last plan as recipe
zx recipe --delete <name>            Delete a recipe
zx recipe --export <name>            Export as .zxrecipe file
zx recipe --import <file>            Import a .zxrecipe file
zx recipe explore [query]            Browse community recipes
zx recipe --share <name>             Share recipe to community
zx recipe --install <cat/name>       Install community recipe

zx playbook list                     List local + community playbooks
zx playbook <name>                   Run a playbook
zx playbook share --name <name>      Share playbook to community

zx undo [--steps N] [--dry-run]      Undo last plan

zx fix [description]                 Diagnose and fix errors
                                     (also accepts piped input + playbook matching)

zx alias suggest                     AI-powered alias suggestions
zx alias list                        List saved aliases
zx alias add --name <n> --command <c>  Add alias manually
zx alias "description"               Create alias from natural language
zx alias install                     Install to shell profile

zx snapshot take [name]              Take a snapshot
zx snapshot list                     List snapshots
zx snapshot diff [name]              Diff current vs snapshot
zx snapshot show <name>              Show snapshot details
zx snapshot delete <name>            Delete a snapshot

zx learn [topic]                     Start a lesson
zx learn --progress                  Show skill tree

zx narrate "command"                 Execute with live AI commentary

zx remote add <name> <user@host>     Add remote host
zx remote remove <name>              Remove remote host
zx remote list                       List remotes
zx @<name> "prompt"                  Execute on remote host
zx @all "prompt"                     Execute on all remotes

zx --version                         Show version
```

---

## Configuration

### Setup Wizard

```bash
zx setup
```

Configures:
- **AI Provider** — select from Gemini, OpenRouter, OpenAI, Anthropic, Ollama, vLLM, or custom
- **API Key** — per-provider, validated on save
- **Default Model** — e.g., `gemini/gemini-2.0-flash-lite`, `ollama_chat/gemma3`
- **Monthly Budget** — spending limit ($0 = unlimited)
- **Session Budget** — per-session spending limit ($0 = unlimited)
- **Show Cost** — display cost summary after each AI-powered run
- **Auto-approve** — skip confirmation for non-dangerous commands
- **Clean mode** — persistent plain-text output
- **Community opt-out** — disable anonymous success reporting for shared recipes

### Environment Variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google Gemini API key |
| `OPENROUTER_API_KEY` | OpenRouter API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `ZX_CLEAN` | Set to `1` to enable clean mode |

### Files

| Path | Purpose |
|------|---------|
| `~/.zx/config.json` | Provider keys, model, budget, preferences |
| `~/.zx/usage.json` | AI usage tracking (tokens, cost, per-model, daily) |
| `~/.zx/history.json` | Command history (last 500) |
| `~/.zx/last_plan.json` | Last executed plan (for undo) |
| `~/.zx/recipes/` | Saved workflow recipes |
| `~/.zx/playbooks/` | Local incident playbooks |
| `~/.zx/community/` | Downloaded community recipes & playbooks |
| `~/.zx/community_index.json` | Cached community catalog |
| `~/.zx/snapshots/` | Context snapshots |
| `~/.zx/aliases.json` | Generated aliases |
| `~/.zx/remotes.json` | Remote host configurations |
| `~/.zx/learner_profile.json` | Shell tutor progress |

---

## How It Works

```
You: "set up a flask project"
         |
         v
   +---------------+
   |  System Recon  | <-- detects OS, shell, installed tools, project type
   +-------+-------+
           v
   +---------------+
   |  AI Planning   | <-- LiteLLM dispatches to your chosen provider
   +-------+-------+
           v
   +---------------+
   | Risk Analysis  | <-- each command scored SAFE -> DANGEROUS
   +-------+-------+
           v
   +---------------+
   |  You Approve   | <-- review plan table, approve/edit/cancel
   +-------+-------+
           v
   +---------------+
   |   Execute      | <-- step by step with streaming output
   +-------+-------+
           v
   +---------------+
   |  Adapt/Undo    | <-- if a step fails, AI re-plans automatically
   +-------+-------+
           v
   +---------------+
   |  Cost Tracked  | <-- tokens, cost, model logged to usage.json
   +---------------+
```

---

## Cross-Platform

zx detects your environment and generates the right commands:

- **bash / zsh** — POSIX syntax, `&&` chaining
- **PowerShell** — cmdlets, `;` chaining (not `&&`)
- **cmd.exe** — native Windows commands
- **Remote hosts** — detects remote OS/shell before generating

---

## Requirements

- Python 3.10+
- An API key for your chosen provider, **or** a local model via [Ollama](https://ollama.com) (free, no key needed)

## License

MIT — [Association for Emerging Technologies (AET)](https://github.com/vcpandya/aicmd)
