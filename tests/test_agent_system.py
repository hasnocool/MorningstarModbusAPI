from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / ".agents" / "skills"

SKILLS = (
    "project-orientation",
    "read-only-modbus-development",
    "catalog-and-intelligence",
    "hardware-verification-replay",
    "device-lifecycle-reconnect",
    "telemetry-history-storage",
    "system-topology-and-power",
    "api-development",
    "catalog-maintenance-provenance",
    "testing-and-ci",
    "documentation-and-release",
    "pr-review-and-integration",
)

SPECIALISTS = (
    "project-maintainer",
    "catalog-specialist",
    "verification-specialist",
    "system-specialist",
    "reviewer",
)


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} is missing YAML frontmatter"
    _, raw, body = text.split("---", 2)
    assert body.strip(), f"{path} has no skill/agent body"
    values: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line or line.startswith((" ", "\t")):
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"\'')
    return values


def test_all_canonical_skills_exist_and_have_unique_names() -> None:
    names: list[str] = []
    for skill in SKILLS:
        path = SKILL_ROOT / skill / "SKILL.md"
        assert path.is_file(), f"missing canonical skill: {path}"
        metadata = _frontmatter(path)
        assert metadata.get("name") == skill
        assert metadata.get("description"), f"{path} needs a discoverable description"
        names.append(metadata["name"])
    assert len(names) == len(set(names))


def test_root_agent_router_references_every_canonical_skill() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for skill in SKILLS:
        assert f".agents/skills/{skill}/SKILL.md" in agents
    assert "read-only" in agents.casefold()
    assert "testing-and-ci" in agents


def test_root_agent_context_tracks_current_domain_architecture_and_system_model() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    required = (
        "transports/",
        "protocol/",
        "controllers/",
        "persistence/",
        "history/",
        "systems/",
        "api/routers/",
        "controller_uid",
        "ReadyEdge",
        "component graph",
        "observed",
        "derived",
        "unknown",
    )
    for token in required:
        assert token in agents, f"AGENTS.md is missing current architecture concept: {token}"


def test_harness_adapters_point_back_to_canonical_context() -> None:
    adapters = (
        ROOT / "CLAUDE.md",
        ROOT / ".github" / "copilot-instructions.md",
        ROOT / ".omp" / "AGENTS.md",
        ROOT / ".pi" / "APPEND_SYSTEM.md",
    )
    for path in adapters:
        text = path.read_text(encoding="utf-8")
        assert "AGENTS.md" in text, f"{path} must route to canonical project context"
        assert ".agents" in text, f"{path} must route to shared project skills/index"
        assert "system-topology-and-power" in text, f"{path} must expose the current system skill"


def test_specialist_agents_exist_for_claude_copilot_and_opencode() -> None:
    patterns = (
        ".claude/agents/{name}.md",
        ".github/agents/{name}.agent.md",
        ".opencode/agents/{name}.md",
    )
    for name in SPECIALISTS:
        for pattern in patterns:
            path = ROOT / pattern.format(name=name)
            assert path.is_file(), f"missing specialist adapter: {path}"
            metadata = _frontmatter(path)
            assert metadata.get("description"), f"{path} needs a description"
            assert "AGENTS.md" in path.read_text(encoding="utf-8")


def test_system_specialist_and_skill_preserve_unknown_measurements() -> None:
    paths = (
        SKILL_ROOT / "system-topology-and-power" / "SKILL.md",
        ROOT / ".claude" / "agents" / "system-specialist.md",
        ROOT / ".github" / "agents" / "system-specialist.agent.md",
        ROOT / ".opencode" / "agents" / "system-specialist.md",
        ROOT / ".github" / "instructions" / "systems.instructions.md",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8").casefold()
        assert "controller_uid" in text
        assert "readyedge" in text
        assert "unknown" in text
        assert "battery net" in text


def test_copilot_path_instructions_have_apply_to_frontmatter() -> None:
    paths = sorted((ROOT / ".github" / "instructions").glob("*.instructions.md"))
    assert paths
    for path in paths:
        metadata = _frontmatter(path)
        assert metadata.get("applyTo"), f"{path} is missing applyTo"


def test_agent_instructions_do_not_pin_temporary_pr_numbers_or_commit_shas() -> None:
    paths = [
        ROOT / "AGENTS.md",
        ROOT / "CLAUDE.md",
        ROOT / ".agents" / "README.md",
        ROOT / "docs" / "agent-system.md",
    ]
    paths.extend(SKILL_ROOT.glob("*/SKILL.md"))
    temporary_pr = re.compile(r"\bPR\s*#\d+\b", re.IGNORECASE)
    commit_sha = re.compile(r"\b[0-9a-f]{40}\b", re.IGNORECASE)
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert not temporary_pr.search(text), f"{path} pins temporary PR state"
        assert not commit_sha.search(text), f"{path} pins a commit SHA"
