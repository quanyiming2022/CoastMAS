"""Validate audit consistency and actual evidence; this is not product acceptance."""
from pathlib import Path
from collections import Counter
import hashlib, json, re, struct, subprocess, xml.etree.ElementTree as ET
ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "docs/audit"
E = ROOT / ".review/evidence/runs/v3-audit-20260925"
data = json.loads((D / "COASTMAS-V3-FINDINGS.json").read_text())
errors = []
def require(value, message):
    if not value: errors.append(message)
def exists(reference):
    require((ROOT / reference.split("#")[0]).is_file(), "Missing evidence: " + reference)
statuses = set(data["status_vocabulary"])
tests = {"PASS", "FAIL", "BLOCKED", "NOT_RUN"}
findings = {x["id"]: x for x in data["findings"]}
require(len(findings) == 35, "35 distinct findings")
fields = {"id", "module", "locations", "design_requirement", "current_behavior", "evidence", "root_cause", "severity", "type", "impact", "recommendation", "dependencies", "blocks_downstream", "acceptance_criteria"}
severities = {"P0_BLOCKER", "P1_MAJOR", "P2_NORMAL", "P3_POLISH"}
types = {"IA_DRIFT", "BUSINESS_LOGIC", "MISSING_IMPLEMENTATION", "BROKEN_INTERACTION", "SCIENTIFIC_ERROR", "API_CONTRACT", "DATABASE_MODEL", "ERROR_HANDLING", "SECURITY", "PERFORMANCE", "UX", "VISUAL", "TECH_DEBT"}
for f in findings.values():
    require(fields <= f.keys(), "Missing finding fields: " + f["id"])
    require(f["severity"] in severities and f["type"] in types, "Finding enum: " + f["id"])
    require(set(f["dependencies"]) <= findings.keys(), "Unknown dependency: " + f["id"])
    for e in f["evidence"]: exists(e)
def acyclic(key, path=()):
    if key in path:
        errors.append("Dependency cycle: " + " -> ".join((*path,key)))
        return
    for dep in findings[key]["dependencies"]: acyclic(dep, (*path,key))
for key in findings: acyclic(key)
for name, count in [("capabilities",177),("navigation",54),("steps",32),("platform_capabilities",18),("original_acceptance_index",145)]:
    require(len(data[name])==count, name+" count")
for name in ["capabilities", "steps", "platform_capabilities"]:
    for row in data[name]:
        require(row["status"] in statuses, "Invalid capability state")
        require(set(row.get("finding_ids", [])) <= findings.keys(), "Unknown finding reference")
        evidence = row.get("evidence", [])
        for e in ([evidence] if isinstance(evidence,str) else evidence): exists(e)
for row in data["original_acceptance_index"]:
    require(row["status"] in tests, "Invalid test state: " + row["id"])
    require(row["status"]!="PASS" or bool(row["evidence"]), "PASS without evidence")
    evidence=row["evidence"]
    for e in ([evidence] if isinstance(evidence,str) else evidence): exists(e)
require(len({x["code"] for x in data["capabilities"]})==177,"Duplicate capability IDs")
require(len({x["id"] for x in data["original_acceptance_index"]})==145,"Duplicate acceptance IDs")
require(dict(Counter(x["status"] for x in data["capabilities"]))==data["counts"]["capability_status"], "Status counts stale")
for p in [*D.glob("*.md"), *(ROOT/".review").glob("*.md")]:
    for ref in re.findall(r'\[[^\]]*\]\(([^)]+)\)', p.read_text()):
        if "://" not in ref and not ref.startswith("#"):
            require((p.parent/ref.split("#")[0]).exists(), f"Broken link: {p.name} -> {ref}")
fixture = ROOT / "scripts/audit_v3/fixtures"
for name, digest in json.loads((fixture/"manifest.json").read_text())["files"].items():
    require(hashlib.sha256((fixture/name).read_bytes()).hexdigest()==digest, "Fixture hash: "+name)
tree=ET.parse(E/"backend-junit.xml")
cases=list(tree.iter("testcase"))
require(len(cases)==290 and not list(tree.iter("failure")) and not list(tree.iter("error")), "Backend results")
front=json.loads((E/"frontend-tests.json").read_text())
require(front["numPassedTests"]==72 and front["numFailedTests"]==0,"Frontend results")
reg=json.loads((E/"final-regression.json").read_text())
require(reg["stats"]["expected"]==6 and reg["stats"]["unexpected"]==0,"Final browser results")
image_sizes={}
for width,height in [(1440,900),(1366,768),(1920,1080),(2560,1440)]:
    png=ROOT/f".review/evidence/screenshots/v3-audit-20260925/settled-result-{width}.png"
    size=struct.unpack(">II",png.read_bytes()[16:24]);require(size==(width,height),"Screenshot dimensions")
    image_sizes[str(width)]=size
# Product paths must still match the audited commit. Docs, scripts and evidence are the only changes.
product=subprocess.check_output(["git","diff",data["before_commit"],"--name-only","--","next/src","next/web/src","next/vendor","next/tests","next/web/e2e","src"],cwd=ROOT,text=True).strip()
require(not product,"Product code changed during diagnostic task")
result={"status":"FAIL" if errors else "PASS","scope":"audit-document/evidence consistency, not full V3 acceptance","audited_commit":data["before_commit"],"findings":len(findings),"capabilities":177,"original_acceptance_statuses":dict(Counter(x["status"] for x in data["original_acceptance_index"])),"product_code_unchanged":not product,"backend_passed":len(cases),"frontend_passed":front["numPassedTests"],"browser_passed":reg["stats"]["expected"],"screenshot_dimensions":image_sizes,"errors":errors}
(E/"audit-validation.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(result,ensure_ascii=False,indent=2))
raise SystemExit(bool(errors))
