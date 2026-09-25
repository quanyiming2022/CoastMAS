"""Validate original package hashes and new numerical evidence before exposing a runtime."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')]
from coastmas_next.models import Release


def main():
    source=ROOT.parent.parent/'data_quan/model/投影寻踪模型_R代码'
    old=ROOT.parent/'artifacts/runtime/projection-release-20260923-v1'
    manifest=json.loads((old/'source-manifest.json').read_text())
    for name,expected in manifest.items():
        path=source/name if name.startswith(('PPCI-master/','pprRFA-master/')) else ROOT.parent/'runtime/projection-pursuit'/name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('Original source or runner changed: '+name)
    image=json.loads((old/'release.json').read_text())['image']
    metadata=json.loads(subprocess.check_output(['docker','image','inspect',image],text=True))[0]
    source_hash=hashlib.sha256((old/'source-manifest.json').read_bytes()).hexdigest()
    if metadata['Config']['Labels']['coastmas.source_sha256']!=source_hash:
        raise ValueError('Image/source attestation mismatch')
    proof_path=ROOT/'artifacts/provided-model-new-proof.json'
    proof=json.loads(proof_path.read_text())
    if proof['image']!=image or proof['clustering_pair_disagreements']!=0 or proof['regression_max_abs_error']>1e-12:
        raise ValueError('New numerical verification did not pass')
    catalog=[Release(model_id=model,image=image,source_sha256=source_hash,proof_sha256=hashlib.sha256(proof_path.read_bytes()).hexdigest(),package=package,version=proof['packages'][package]).model_dump() for model,package in [('ppci_mcdc','PPCI'),('ppr_ols','pprRFA')]]
    target=ROOT/'.state/verified-runtimes.json'
    if target.exists():raise ValueError('Runtime catalog exists; explicit new version required')
    target.write_text(json.dumps(catalog,indent=2))
    (ROOT/'artifacts/new-runtime-attestation.json').write_text(json.dumps({'source_files_verified':len(manifest),'image':image,'source_sha256':source_hash,'new_proof_sha256':hashlib.sha256(proof_path.read_bytes()).hexdigest(),'approvals_inherited':False},indent=2))
    print('Verified new runtime catalog installed; no project approval granted')

if __name__=='__main__':main()
