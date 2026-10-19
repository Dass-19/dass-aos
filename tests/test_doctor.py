"""Tests for `aos doctor` (read-only harness audit, ADR-008)."""
import shutil
import tempfile
import unittest
from pathlib import Path

from dass_aos.bootstrap import init_project
from dass_aos.doctor import collect_findings, run_doctor


def levels(findings, area_contains):
    return {f.level for f in findings if area_contains in f.area}


class TestDoctor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        init_project(self.temp_dir, project_name="test-project", tools=["claude-code"])

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_healthy_project_has_no_errors(self):
        findings = collect_findings(self.temp_dir)
        self.assertEqual([f for f in findings if f.level == "error"], [])

    def test_skill_without_description_is_an_error(self):
        bad = self.temp_dir / ".aos" / "skills" / "specs" / "mio.md"
        bad.write_text('---\nname: "mio"\n---\n', encoding="utf-8")
        findings = collect_findings(self.temp_dir)
        self.assertIn("error", levels(findings, "mio.md"))

    def test_skill_name_must_match_the_file(self):
        bad = self.temp_dir / ".aos" / "skills" / "specs" / "mio.md"
        bad.write_text('---\nname: "otro"\ndescription: "x"\ncost: on-demand\n---\n', encoding="utf-8")
        findings = collect_findings(self.temp_dir)
        self.assertTrue(any("no coincide con el archivo" in f.message for f in findings))

    def test_unconditional_skill_is_always_listed(self):
        skill = self.temp_dir / ".aos" / "skills" / "specs" / "propia.md"
        skill.write_text('---\nname: "propia"\ndescription: "x"\ncost: on-demand\n---\n\n# Skill: propia\n', encoding="utf-8")
        findings = collect_findings(self.temp_dir)
        self.assertEqual([f for f in findings if f.area == "propia.md"], [])

    def test_malformed_applies_when_is_an_error_not_a_crash(self):
        broken = self.temp_dir / ".aos" / "skills" / "specs" / "rota.md"
        broken.write_text(
            '---\nname: "rota"\ndescription: "x"\ncost: on-demand\napplies_when: [no-es-json\n---\n',
            encoding="utf-8",
        )
        findings = collect_findings(self.temp_dir)
        self.assertTrue(
            any(f.level == "error" and "rota.md" in f.area + f.message for f in findings),
            findings,
        )

    def test_conditional_skill_is_only_informational(self):
        conditional = self.temp_dir / ".aos" / "skills" / "specs" / "condicional.md"
        conditional.write_text(
            '---\nname: "condicional"\ndescription: "x"\ncost: on-demand\n'
            'applies_when: ["nada/**/*.zzz"]\n---\n\n# Skill: condicional\n',
            encoding="utf-8",
        )
        findings = collect_findings(self.temp_dir)
        self.assertEqual(levels(findings, "condicional.md"), {"info"})

    def test_missing_cost_is_a_warning(self):
        spec = self.temp_dir / ".aos" / "skills" / "specs" / "sin-coste.md"
        spec.write_text('---\nname: "sin-coste"\ndescription: "x"\n---\n', encoding="utf-8")
        findings = collect_findings(self.temp_dir)
        self.assertIn("warn", levels(findings, "sin-coste.md"))

    def test_prd_without_trd_is_reported(self):
        from dass_aos.specs import create_new_spec

        create_new_spec(self.temp_dir, kind="prd", title="Huerfana")
        findings = collect_findings(self.temp_dir)
        self.assertTrue(any("sin pareja" in f.message for f in findings))

    def test_orphan_local_addition_is_reported(self):
        orphan = self.temp_dir / ".aos" / "agents" / "inexistente.local.md"
        orphan.write_text("- algo\n", encoding="utf-8")
        findings = collect_findings(self.temp_dir)
        self.assertTrue(any("sin archivo base" in f.message for f in findings))

    def test_missing_deny_paths_is_reported(self):
        import json

        config = self.temp_dir / ".aos" / "config.json"
        data = json.loads(config.read_text(encoding="utf-8"))
        data.pop("deny_paths", None)
        config.write_text(json.dumps(data, indent=2), encoding="utf-8")
        findings = collect_findings(self.temp_dir)
        self.assertTrue(any("deny_paths" in f.message for f in findings))

    def test_run_doctor_is_read_only_and_exit_zero_without_strict(self):
        before = {p: p.read_bytes() for p in self.temp_dir.rglob("*") if p.is_file()}
        code = run_doctor(self.temp_dir)
        after = {p: p.read_bytes() for p in self.temp_dir.rglob("*") if p.is_file()}
        self.assertEqual(code, 0)
        self.assertEqual(before, after)

    def test_strict_exits_one_on_errors(self):
        (self.temp_dir / ".aos" / "skills" / "specs" / "roto.md").write_text("---\n", encoding="utf-8")
        self.assertEqual(run_doctor(self.temp_dir), 0)
        self.assertEqual(run_doctor(self.temp_dir, strict=True), 1)


if __name__ == "__main__":
    unittest.main()
