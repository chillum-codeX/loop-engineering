"""
SKILL.md System Module

Based on Anthropic's Loop Engineering paper (Section IV):
- Skills make project knowledge permanent in a single file (SKILL.md)
- Pays off "intent debt": the price of explaining context over and over
- A skill can be reused and maintained; a wall of prompt cannot

Skill Schema (from paper):
- NAME: Skill identifier
- WHEN: Trigger conditions
- READ: Discovery inputs (what to read)
- JUDGE: Judgment criteria (how to decide)
- OUTPUT: Handoff preparation (task formatting)
- STOP: Boundaries (what NOT to do)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import yaml


@dataclass
class SkillDefinition:
    """
    A skill definition parsed from SKILL.md.

    Skills are project knowledge made permanent, paying off
    "intent debt" - the cost of re-explaining context every turn.
    """
    name: str
    when: str = ""  # Trigger conditions
    read: List[str] = field(default_factory=list)  # Discovery inputs
    judge: str = ""  # Judgment criteria
    output: str = ""  # Handoff preparation
    stop: List[str] = field(default_factory=list)  # Stop boundaries
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Source tracking
    source_file: Optional[Path] = None
    line_number: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert skill to dictionary."""
        return {
            "name": self.name,
            "when": self.when,
            "read": self.read,
            "judge": self.judge,
            "output": self.output,
            "stop": self.stop,
            "metadata": self.metadata,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any], source_file: Optional[Path] = None) -> SkillDefinition:
        """Create skill from dictionary."""
        return SkillDefinition(
            name=data.get("name", "unnamed"),
            when=data.get("when", ""),
            read=data.get("read", []),
            judge=data.get("judge", ""),
            output=data.get("output", ""),
            stop=data.get("stop", []),
            metadata=data.get("metadata", {}),
            source_file=source_file,
        )


class SkillParser:
    """
    Parser for SKILL.md files.

    Supports two formats:
    1. Structured YAML frontmatter
    2. Freeform markdown with section headers
    """

    # Regex patterns for parsing
    YAML_FRONTMATTER = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)
    SECTION_HEADER = re.compile(r'^##?\s*(\w+):?\s*(.*)$', re.MULTILINE)

    @classmethod
    def parse_file(cls, filepath: Union[str, Path]) -> SkillDefinition:
        """Parse a SKILL.md file."""
        filepath = Path(filepath)
        content = filepath.read_text()
        return cls.parse_content(content, source_file=filepath)

    @classmethod
    def parse_content(cls, content: str, source_file: Optional[Path] = None) -> SkillDefinition:
        """Parse SKILL.md content."""
        # Try YAML frontmatter first
        yaml_match = cls.YAML_FRONTMATTER.match(content)
        if yaml_match:
            try:
                data = yaml.safe_load(yaml_match.group(1))
                if isinstance(data, dict):
                    return SkillDefinition.from_dict(data, source_file)
            except yaml.YAMLError:
                pass  # Fall through to markdown parsing

        # Parse as markdown with sections
        return cls._parse_markdown(content, source_file)

    @classmethod
    def _parse_markdown(cls, content: str, source_file: Optional[Path] = None) -> SkillDefinition:
        """Parse markdown-style SKILL.md."""
        skill = SkillDefinition(
            name="unnamed",
            source_file=source_file,
        )

        # Extract NAME from first header
        name_match = re.search(r'^#\s*(?:NAME:\s*)?(.*?)$', content, re.MULTILINE)
        if name_match:
            skill.name = name_match.group(1).strip()

        # Parse sections
        sections = cls._extract_sections(content)

        # Map sections to skill fields
        section_mapping = {
            'when': ['when', 'trigger', 'invocation', 'schedule'],
            'read': ['read', 'inputs', 'discovery', 'sources'],
            'judge': ['judge', 'judgment', 'criteria', 'decision', 'evaluate'],
            'output': ['output', 'handoff', 'write', 'produce'],
            'stop': ['stop', 'boundaries', 'do not', 'limitations'],
        }

        for field_name, section_names in section_mapping.items():
            for section_name in section_names:
                if section_name in sections:
                    value = sections[section_name]
                    if field_name == 'read':
                        # Parse as list
                        skill.read = cls._parse_list(value)
                    elif field_name == 'stop':
                        skill.stop = cls._parse_list(value)
                    else:
                        setattr(skill, field_name, value.strip())
                    break

        return skill

    @classmethod
    def _extract_sections(cls, content: str) -> Dict[str, str]:
        """Extract sections from markdown content."""
        sections = {}
        current_section = None
        current_content = []

        for line in content.split('\n'):
            match = cls.SECTION_HEADER.match(line)
            if match:
                # Save previous section
                if current_section:
                    sections[current_section.lower()] = '\n'.join(current_content).strip()

                # Start new section
                current_section = match.group(1).lower()
                current_content = [match.group(2)] if match.group(2) else []
            elif current_section:
                current_content.append(line)

        # Save last section
        if current_section:
            sections[current_section] = '\n'.join(current_content).strip()

        return sections

    @staticmethod
    def _parse_list(content: str) -> List[str]:
        """Parse content as a list (bullet points or numbered)."""
        items = []
        for line in content.split('\n'):
            line = line.strip()
            # Match bullet points or numbered items
            if re.match(r'^[-*•]|^\d+\.', line):
                item = re.sub(r'^[-*•]|^\d+\.', '', line).strip()
                if item:
                    items.append(item)
            elif line and not items:
                # First non-empty line if no bullets
                items.append(line)
        return items


class SkillLoader:
    """
    Loads and manages skills from the .claude/skills/ directory.

    Directory structure:
        .claude/skills/
            {skill-name}/
                SKILL.md
    """

    def __init__(self, skills_dir: Union[str, Path] = ".claude/skills"):
        self.skills_dir = Path(skills_dir)
        self._skills: Dict[str, SkillDefinition] = {}
        self._loaded = False

    def load_all(self) -> Dict[str, SkillDefinition]:
        """Load all skills from the skills directory."""
        if self._loaded:
            return self._skills

        if not self.skills_dir.exists():
            return {}

        for skill_dir in sorted(self.skills_dir.iterdir()):
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    try:
                        skill = SkillParser.parse_file(skill_file)
                        self._skills[skill.name] = skill
                    except Exception as e:
                        print(f"Warning: Failed to load skill from {skill_file}: {e}")
            elif skill_dir.suffix.lower() == ".md":
                try:
                    skill = SkillParser.parse_file(skill_dir)
                    self._skills[skill.name] = skill
                except Exception as e:
                    print(f"Warning: Failed to load skill from {skill_dir}: {e}")

        self._loaded = True
        return self._skills

    def get_skill(self, name: str) -> Optional[SkillDefinition]:
        """Get a skill by name."""
        if not self._loaded:
            self.load_all()
        return self._skills.get(name)

    def list_skills(self) -> List[str]:
        """List all loaded skill names."""
        if not self._loaded:
            self.load_all()
        return list(self._skills.keys())

    def reload(self) -> None:
        """Reload all skills."""
        self._skills.clear()
        self._loaded = False
        self.load_all()


class SkillValidator:
    """Validates skill definitions for completeness."""

    REQUIRED_FIELDS = ['name', 'when', 'read']
    RECOMMENDED_FIELDS = ['judge', 'output']

    @classmethod
    def validate(cls, skill: SkillDefinition) -> SkillValidationResult:
        """Validate a skill definition."""
        issues = []
        warnings = []

        # Check required fields
        if not skill.name or skill.name == "unnamed":
            issues.append("Skill must have a name")

        if not skill.when:
            issues.append("Skill must specify WHEN (trigger conditions)")

        if not skill.read:
            issues.append("Skill must specify READ (discovery inputs)")

        # Check recommended fields
        if not skill.judge:
            warnings.append("Skill lacks JUDGE criteria - may make poor decisions")

        if not skill.output:
            warnings.append("Skill lacks OUTPUT specification - handoff may be unclear")

        # Check for common anti-patterns
        if not skill.stop:
            warnings.append("Skill lacks STOP boundaries - may overstep scope")

        return SkillValidationResult(
            is_valid=len(issues) == 0,
            issues=issues,
            warnings=warnings,
            skill_name=skill.name,
        )


@dataclass
class SkillValidationResult:
    """Result of skill validation."""
    is_valid: bool
    issues: List[str]
    warnings: List[str]
    skill_name: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "issues": self.issues,
            "warnings": self.warnings,
            "skill_name": self.skill_name,
        }


# Example skills from the paper

EXAMPLE_TRIAGE_SKILL = """
# NAME: morning-triage

## WHEN
Invoked each morning by automation.

## READ
- CI runs that failed since yesterday
- Issues opened in the last 24h
- Commits merged since the last run

## JUDGE
For each item, is it worth acting on? Skip noise. Keep only actionable findings.

## OUTPUT
Write findings + status to ./state/triage.md (one row per finding).

## STOP
- Do not fix issues automatically
- Do not assign to others
- Do not modify production code
"""

EXAMPLE_CODE_REVIEW_SKILL = """
# NAME: code-review

## WHEN
Pull request is opened or updated.

## READ
- PR diff
- Related test files
- Project coding standards

## JUDGE
Does the code:
1. Pass all tests?
2. Follow project conventions?
3. Handle edge cases?
4. Introduce security issues?

## OUTPUT
- Approval if all checks pass
- Detailed feedback if issues found
- Specific line-by-line comments

## STOP
- Do not commit changes
- Do not merge PRs
- Do not modify code directly
"""


def create_example_skills(base_dir: Union[str, Path] = ".claude/skills") -> None:
    """Create example skill files for reference."""
    base_dir = Path(base_dir)

    # Create triage skill
    triage_dir = base_dir / "morning-triage"
    triage_dir.mkdir(parents=True, exist_ok=True)
    (triage_dir / "SKILL.md").write_text(EXAMPLE_TRIAGE_SKILL.strip())

    # Create code review skill
    review_dir = base_dir / "code-review"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "SKILL.md").write_text(EXAMPLE_CODE_REVIEW_SKILL.strip())

    print(f"Created example skills in {base_dir}")
