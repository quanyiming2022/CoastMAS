"""Prepare six existing browser regressions for the audit namespace; never edit originals."""
from pathlib import Path
import argparse, hashlib, json, os, shutil, subprocess
ROOT = Path(__file__).resolve().parents[2]
NAMES = ("desktop-management", "import-recovery", "planning-objects", "unified-methods", "builtin-indicators", "planning-units")
parser = argparse.ArgumentParser()
parser.add_argument("--run", action="store_true", help="Execute against the existing isolated service at 58125")
args = parser.parse_args()
source = ROOT / "next/web/e2e"
target = ROOT / "next/web/.audit-v3"
target.mkdir(exist_ok=True)
evidence = ROOT / ".review/evidence/runs/v3-audit-20260925"
changes = []
for name in NAMES:
    original = (source / f"{name}.spec.ts").read_text()
    text = original.replace("58013", "58125")
    edits = [{"kind": "isolation", "description": "All hardcoded URLs and port guards use 58125, including the second browser."}]
    if name == "desktop-management":
        for label, route in [("项目管理", "/projects"), ("用户管理", "/management/users")]:
            old = f"await page.getByRole('link',{{name:'{label}',exact:true}}).click();"
            assert old in text, old
            text = text.replace(old, f"await page.goto('{route}?project='+access.project_id);")
        edits.append({"kind": "retired_navigation", "description": "Use actual routes for retired labels; navigation is independently audited. Assertions unchanged."})
    if name == "unified-methods":
        old = "await page.getByRole('link',{name:'方法方案',exact:true}).click();"
        assert old in text
        text = text.replace(old, "await expect(page.getByRole('button',{name:'查看或编辑研究名称'})).toHaveText('方法固定引用验收'); const group=page.getByRole('button',{name:'指标与方法',exact:true});if(await group.getAttribute('aria-expanded')!=='true')await group.click();await page.getByRole('link',{name:'综合评价方法',exact:true}).click();")
        edits.append({"kind": "current_navigation", "description": "Wait for current research then use real V3 group and method link. All business assertions preserved."})
    fixture_paths = {
        "/Users/quanyiming/Projects/CoastMAS/next/artifacts/unified-business-20260924/fixtures/coast.tif": "coast.tif",
        "/Users/quanyiming/Projects/CoastMAS/next/artifacts/unified-business-20260924/fixtures/coast.tfw": "coast.tfw",
        "/Users/quanyiming/Projects/CoastMAS/next/artifacts/master-20260925/engineering-red-nir.tif": "engineering-red-nir.tif",
        "/Users/quanyiming/Projects/CoastMAS/next/artifacts/master-20260925/engineering-location.json": "engineering-location.json",
    }
    for old, filename in fixture_paths.items():
        if old in text:
            text = text.replace(old, str(ROOT / "scripts/audit_v3/fixtures" / filename))
            edits.append({"kind": "portable_fixture", "file": filename, "sha256": hashlib.sha256((ROOT / "scripts/audit_v3/fixtures" / filename).read_bytes()).hexdigest()})
    assert "58013" not in text
    (target / f"{name}.spec.ts").write_text(text)
    changes.append({"test": name, "source_sha256": hashlib.sha256(original.encode()).hexdigest(), "diagnostic_sha256": hashlib.sha256(text.encode()).hexdigest(), "adaptations": edits})
shutil.copyfile(source / "evidence.ts", target / "evidence.ts")
(target / "playwright.config.ts").write_text("import {defineConfig} from '@playwright/test';export default defineConfig({testDir:'.',outputDir:'../../artifacts/v3-audit-playwright',workers:1,retries:0,reporter:[['line'],['json',{outputFile:'../../../.review/evidence/runs/v3-audit-20260925/final-regression.json'}]],use:{baseURL:'http://127.0.0.1:58125',channel:'chromium',trace:'off',screenshot:'only-on-failure',actionTimeout:15000}});\n")
(evidence / "test-adaptations-final.json").write_text(json.dumps(changes, ensure_ascii=False, indent=2) + "\n")
print("Prepared six diagnostic copies; production tests unchanged.")
if args.run:
    env = dict(os.environ, COASTMAS_NEXT_TEST_URL="http://127.0.0.1:58125", COASTMAS_NEXT_ACCESS_FILE=str(ROOT / "next/.state/v3-audit-20260925/settings-access.json"), COASTMAS_NEXT_EVIDENCE_DIR=str(evidence / "final-regression"))
    raise SystemExit(subprocess.call(["./node_modules/.bin/playwright", "test", "--config", ".audit-v3/playwright.config.ts"], cwd=ROOT / "next/web", env=env))
