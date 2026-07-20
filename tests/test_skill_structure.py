"""Architecture contracts for the skill package."""

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
ROOT_SKILL = ROOT / "SKILL.md"
WORKFLOW_REFERENCES = {
    "references/search-and-disambiguate.md",
    "references/build-note.md",
    "references/validate-import.md",
    "references/literature-synthesis.md",
    "references/backfill-overviews.md",
    "references/research-plan.md",
}


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, f"missing YAML frontmatter: {path}"
    return yaml.safe_load(match.group(1))


def test_root_is_the_only_skill_entrypoint():
    assert ROOT_SKILL.is_file()
    legacy_skills = ROOT / "skills"
    assert not legacy_skills.exists() or not list(legacy_skills.rglob("SKILL.md"))


def test_root_frontmatter_has_only_trigger_fields():
    metadata = _frontmatter(ROOT_SKILL)
    assert set(metadata) == {"name", "description"}
    assert metadata["name"] == ROOT.name


def test_root_links_every_workflow_reference():
    text = ROOT_SKILL.read_text(encoding="utf-8")
    linked = set(re.findall(r"\]\((references/[^)#]+\.md)\)", text))
    assert WORKFLOW_REFERENCES <= linked
    all_references = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "references").glob("*.md")
    }
    assert all_references <= linked


def test_all_root_local_links_resolve_inside_skill():
    text = ROOT_SKILL.read_text(encoding="utf-8")
    targets = re.findall(r"\]\((?!https?://)([^)#]+)(?:#[^)]+)?\)", text)
    for target in targets:
        resolved = (ROOT / target).resolve()
        assert resolved.is_relative_to(ROOT)
        assert resolved.is_file(), f"broken link: {target}"


def test_all_reference_links_resolve_inside_skill():
    for document in (ROOT / "references").glob("*.md"):
        text = document.read_text(encoding="utf-8")
        targets = re.findall(r"\]\((?!https?://)([^)#]+)(?:#[^)]+)?\)", text)
        for target in targets:
            resolved = (document.parent / target).resolve()
            assert resolved.is_relative_to(ROOT)
            assert resolved.is_file(), f"broken link in {document.name}: {target}"


def test_workflow_references_are_not_nested_skills():
    for relative_path in WORKFLOW_REFERENCES:
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        assert text.startswith("# ")
        assert not text.startswith("---\n")


def test_long_references_have_a_table_of_contents():
    for path in (ROOT / "references").glob("*.md"):
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > 100:
            assert "## Contents" in lines[:30], f"missing contents: {path.name}"


def test_openai_default_prompt_invokes_root_skill():
    metadata = yaml.safe_load(
        (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8"))
    prompt = metadata["interface"]["default_prompt"]
    assert f"${ROOT.name}" in prompt


def test_workflow_commands_use_a_verified_python_interpreter():
    root_text = ROOT_SKILL.read_text(encoding="utf-8")
    assert "Probe the interpreter" in root_text
    assert "`PYTHON_CMD`" in root_text

    workflow_docs = [ROOT_SKILL, *(ROOT / "references").glob("*.md")]
    for document in workflow_docs:
        text = document.read_text(encoding="utf-8")
        assert not re.search(
            r"^python -m alphaxiv_workflow\.", text, re.MULTILINE
        ), f"bare Python command in {document.name}"
