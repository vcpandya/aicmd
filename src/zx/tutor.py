"""Shell Tutor for zx — interactive learning mode with concept tracking."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import CONFIG_DIR

PROFILE_FILE = CONFIG_DIR / "learner_profile.json"

# Concept categories and their topics
CONCEPT_TREE = {
    "basics": {
        "label": "Shell Basics",
        "topics": [
            "navigation",       # cd, pwd, ls
            "file_operations",  # cp, mv, rm, mkdir, touch
            "viewing_files",    # cat, head, tail, less
            "permissions",      # chmod, chown
            "help_system",      # man, --help, info
        ],
    },
    "text_processing": {
        "label": "Text Processing",
        "topics": [
            "grep_search",      # grep, rg
            "sed_awk",          # sed, awk
            "sort_uniq",        # sort, uniq, wc
            "pipes",            # |, >, >>, <
            "redirection",      # stdin, stdout, stderr
        ],
    },
    "system": {
        "label": "System Administration",
        "topics": [
            "process_mgmt",    # ps, top, kill, jobs, bg, fg
            "disk_space",      # df, du, mount
            "networking",      # curl, wget, ping, netstat, ssh
            "users_groups",    # whoami, groups, sudo, su
            "services",        # systemctl, service
        ],
    },
    "development": {
        "label": "Development Tools",
        "topics": [
            "git_basics",      # git add, commit, push, pull
            "git_advanced",    # rebase, cherry-pick, stash, bisect
            "package_mgmt",    # pip, npm, cargo, apt, brew
            "containers",      # docker, docker-compose, kubectl
            "debugging",       # strace, lsof, tcpdump
        ],
    },
    "scripting": {
        "label": "Scripting",
        "topics": [
            "variables",       # $VAR, export, env
            "conditionals",    # if, test, [[ ]]
            "loops",           # for, while, until
            "functions",       # function def, local, return
            "error_handling",  # set -e, trap, exit codes
        ],
    },
}


def load_profile() -> dict:
    """Load or create the learner profile."""
    if PROFILE_FILE.exists():
        try:
            return json.loads(PROFILE_FILE.read_text())
        except (json.JSONDecodeError, TypeError):
            pass

    # Create default profile
    profile = {
        "created": datetime.now(timezone.utc).isoformat(),
        "mastered": [],           # List of topic IDs the learner has mastered
        "in_progress": [],        # Topics being learned
        "lessons_completed": 0,
        "last_topic": "",
        "history": [],            # List of {"topic": ..., "timestamp": ..., "score": ...}
    }
    return profile


def save_profile(profile: dict) -> None:
    """Save the learner profile."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_FILE.write_text(json.dumps(profile, indent=2))


def get_next_topic(profile: dict) -> Optional[str]:
    """Suggest the next topic to learn based on profile."""
    mastered = set(profile.get("mastered", []))

    # Walk through the concept tree in order
    for category_id, category in CONCEPT_TREE.items():
        for topic in category["topics"]:
            if topic not in mastered:
                return topic
    return None  # All mastered!


def get_topic_category(topic_id: str) -> Optional[str]:
    """Find which category a topic belongs to."""
    for cat_id, cat in CONCEPT_TREE.items():
        if topic_id in cat["topics"]:
            return cat_id
    return None


def get_topic_label(topic_id: str) -> str:
    """Get a human-readable label for a topic."""
    labels = {
        "navigation": "Navigation (cd, pwd, ls)",
        "file_operations": "File Operations (cp, mv, rm, mkdir)",
        "viewing_files": "Viewing Files (cat, head, tail, less)",
        "permissions": "File Permissions (chmod, chown)",
        "help_system": "Help System (man, --help)",
        "grep_search": "Searching with grep",
        "sed_awk": "Text Transformation (sed, awk)",
        "sort_uniq": "Sorting & Counting (sort, uniq, wc)",
        "pipes": "Pipes & Command Chaining",
        "redirection": "I/O Redirection (>, >>, <, 2>)",
        "process_mgmt": "Process Management (ps, kill, jobs)",
        "disk_space": "Disk Space (df, du)",
        "networking": "Networking (curl, ping, ssh)",
        "users_groups": "Users & Permissions (sudo, su)",
        "services": "System Services (systemctl)",
        "git_basics": "Git Basics (add, commit, push)",
        "git_advanced": "Git Advanced (rebase, stash, bisect)",
        "package_mgmt": "Package Managers (pip, npm, apt)",
        "containers": "Containers (docker, kubectl)",
        "debugging": "Debugging Tools (strace, lsof)",
        "variables": "Shell Variables & Environment",
        "conditionals": "Conditionals (if, test)",
        "loops": "Loops (for, while)",
        "functions": "Functions & Scripts",
        "error_handling": "Error Handling (set -e, trap)",
    }
    return labels.get(topic_id, topic_id.replace("_", " ").title())


def mark_topic_mastered(profile: dict, topic_id: str) -> None:
    """Mark a topic as mastered."""
    if topic_id not in profile.get("mastered", []):
        profile.setdefault("mastered", []).append(topic_id)
    if topic_id in profile.get("in_progress", []):
        profile["in_progress"].remove(topic_id)
    save_profile(profile)


def record_lesson(profile: dict, topic_id: str, score: int = 1) -> None:
    """Record a completed lesson."""
    profile["lessons_completed"] = profile.get("lessons_completed", 0) + 1
    profile["last_topic"] = topic_id
    profile.setdefault("history", []).append({
        "topic": topic_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "score": score,
    })
    if topic_id not in profile.get("in_progress", []) and topic_id not in profile.get("mastered", []):
        profile.setdefault("in_progress", []).append(topic_id)
    save_profile(profile)


def get_progress_display(profile: dict) -> list[str]:
    """Generate a skill tree display."""
    mastered = set(profile.get("mastered", []))
    in_progress = set(profile.get("in_progress", []))
    lines = []

    total_topics = sum(len(c["topics"]) for c in CONCEPT_TREE.values())
    total_mastered = len(mastered)
    pct = (total_mastered / total_topics * 100) if total_topics else 0

    lines.append(f"  Shell Mastery: {total_mastered}/{total_topics} topics ({pct:.0f}%)")
    lines.append(f"  Lessons completed: {profile.get('lessons_completed', 0)}")
    lines.append("")

    # Progress bar
    bar_width = 30
    filled = int(bar_width * pct / 100)
    bar = "#" * filled + "-" * (bar_width - filled)
    lines.append(f"  [{bar}] {pct:.0f}%")
    lines.append("")

    for cat_id, cat in CONCEPT_TREE.items():
        cat_mastered = sum(1 for t in cat["topics"] if t in mastered)
        cat_total = len(cat["topics"])
        lines.append(f"  {cat['label']} ({cat_mastered}/{cat_total}):")

        for topic in cat["topics"]:
            if topic in mastered:
                status = "[x]"
            elif topic in in_progress:
                status = "[~]"
            else:
                status = "[ ]"
            lines.append(f"    {status} {get_topic_label(topic)}")
        lines.append("")

    return lines


def run_tutor(
    topic: str = "",
    show_progress: bool = False,
    ai_client=None,
) -> None:
    """Main tutor flow.

    Args:
        topic: Specific topic to learn (or empty for next suggested)
        show_progress: Show skill tree / progress
        ai_client: AIClient for generating lessons
    """
    from .ui import print_banner, print_success, print_error, print_warning, print_info, show_spinner, is_clean_mode

    print_banner()
    profile = load_profile()

    if show_progress:
        lines = get_progress_display(profile)
        for line in lines:
            print_info(line)
        return

    # Determine topic
    if not topic:
        topic = get_next_topic(profile)
        if not topic:
            print_success("You've mastered all topics! You're a shell wizard!")
            return
        print_info(f"  Suggested next topic: {get_topic_label(topic)}")
    else:
        # Find matching topic
        matched = None
        for cat in CONCEPT_TREE.values():
            for t in cat["topics"]:
                if topic.lower() in t.lower() or topic.lower() in get_topic_label(t).lower():
                    matched = t
                    break
            if matched:
                break
        if not matched:
            print_error(f"Topic '{topic}' not found. Use 'zx learn --progress' to see all topics.")
            return
        topic = matched

    if not ai_client:
        print_error("AI client required for interactive lessons.")
        return

    # Generate lesson
    mastered = profile.get("mastered", [])
    mastered_labels = [get_topic_label(t) for t in mastered]

    with show_spinner("thinking"):
        try:
            lesson = ai_client.generate_lesson(
                topic_id=topic,
                topic_label=get_topic_label(topic),
                mastered_topics=mastered_labels,
                shell_info=ai_client.shell_info,
            )
        except Exception as e:
            print_error(f"Could not generate lesson: {e}")
            return

    # Display lesson
    print_info(f"\n  === Lesson: {get_topic_label(topic)} ===\n")
    print_info(f"  {lesson.explanation}")
    print_info("")

    if lesson.examples:
        print_info("  Examples:")
        for ex in lesson.examples:
            print_info(f"    $ {ex}")
        print_info("")

    if lesson.exercise:
        print_info(f"  Exercise: {lesson.exercise}")
        print_info("")

    if lesson.tips:
        print_info("  Tips:")
        for tip in lesson.tips:
            print_info(f"    - {tip}")
        print_info("")

    # Record lesson
    record_lesson(profile, topic)

    # Ask if mastered
    if is_clean_mode():
        choice = input("  Mark as mastered? [y/N]: ").strip().lower()
    else:
        from rich.prompt import Prompt
        choice = Prompt.ask("  Mark as mastered?", choices=["y", "n"], default="n", show_choices=False)

    if choice == "y":
        mark_topic_mastered(profile, topic)
        print_success(f"Topic '{get_topic_label(topic)}' mastered!")

        # Suggest next
        next_topic = get_next_topic(profile)
        if next_topic:
            print_info(f"  Next suggested topic: {get_topic_label(next_topic)}")
    else:
        print_info("  Topic saved as in-progress. Come back anytime!")
