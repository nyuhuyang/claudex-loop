"""Validate distributable skill metadata, references and provider manifests."""
import json
from pathlib import Path
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHECKBOX_SECTIONS = re.compile(r"progress checklist|acceptance criteria|verification", re.I)


def plan_checkbox_errors(text):
    """List items under checkbox sections (and their subheadings) that are not `- [ ]`/`- [x]`."""
    errors, level = [], None
    text = re.sub(r"```.*?```", lambda m: "\n" * m.group().count("\n"), text, flags=re.S)
    for number, line in enumerate(text.splitlines(), 1):
        heading = re.match(r"(#+)\s+(.*)", line)
        if heading:
            depth = len(heading.group(1))
            if level is None or depth <= level:
                level = depth if CHECKBOX_SECTIONS.match(heading.group(2)) else None
        elif level and re.match(r"\s*(?:[-*+]|\d+[.)])\s", line) \
                and not re.match(r"\s*[-*+] \[[ xX]\]\s", line):
            errors.append(f"line {number}: list item is not a checkbox: {line.strip()[:60]}")
    return errors


def validate(root=ROOT):
    errors = []
    for path in sorted((root / "skills").glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        try:
            if not text.startswith("---\n"):
                raise ValueError("missing frontmatter (or UTF-8 BOM present)")
            front = yaml.safe_load(text.split("---", 2)[1])
            if front.get("name") != path.parent.name:
                raise ValueError("name must match the skill folder")
            description = front.get("description")
            if not isinstance(description, str) or not description.strip() or len(description) > 1024:
                raise ValueError("description must be a nonempty string of at most 1024 characters")
        except (ValueError, IndexError, AttributeError, yaml.YAMLError) as exc:
            errors.append(f"{path.relative_to(root)}: {exc}")
    # Validate links in active instructions and public README, excluding fenced code.
    for path in [root / "README.md", *(root / "skills").rglob("*.md")]:
        text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
        for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
            if re.match(r"[a-z]+://|#", link):
                continue
            target = link.split("#", 1)[0]
            if target and not (path.parent / target).exists():
                errors.append(f"{path.relative_to(root)}: missing reference {link}")
    for path in sorted((root / "docs/exec-plans/active").glob("*.md")):
        if "review-log" not in path.name:
            errors += [f"{path.relative_to(root)}: {e}"
                       for e in plan_checkbox_errors(path.read_text(encoding="utf-8"))]
    for folder in (".claude-plugin", ".codex-plugin"):
        try:
            manifest = json.loads((root / folder / "plugin.json").read_text(encoding="utf-8"))
            if manifest.get("name") != "claudex-loop" or not manifest.get("version"):
                errors.append(f"{folder}: missing name/version")
        except (OSError, ValueError) as exc:
            errors.append(f"{folder}: {exc}")
    marketplace = json.loads((root / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    if marketplace["plugins"][0]["name"] != "claudex-loop":
        errors.append("Claude marketplace plugin name mismatch")
    if not (root / "skills/claudex-loop/scripts/runner.py").is_file():
        errors.append("Missing shared runner")
    return errors


if __name__ == "__main__":
    failures = validate()
    print("\n".join(failures) if failures else "Skill metadata, references and manifests passed.")
    sys.exit(bool(failures))
