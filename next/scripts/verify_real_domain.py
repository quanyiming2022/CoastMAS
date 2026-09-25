"""Isolated real-file engineering acceptance, never a formal coastal conclusion."""
import hashlib
import json
import resource
import secrets
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')]
from coastmas_next.app import create_app
from coastmas_next.config import Settings
from coastmas_next.contracts import TaskDraft
from coastmas_next.execution import Execution
from coastmas_next.intake import Intake
from coastmas_next.models import ModelRegistry
from coastmas_next.store import Store
from coastmas_next.worker import Worker


def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as source:
        while chunk:=source.read(1024**2):value.update(chunk)
    return value.hexdigest()


def main():
    proof_path=ROOT/'artifacts/small-full-domain-proof.json'
    proof=json.loads(proof_path.read_text())
    if proof['runner_sha256']!=digest(ROOT/'runtime/stream.R') or any(m['status']!='PASS' or m['fit_count']!=1 for m in proof['models']):
        raise ValueError('New application proof is missing or stale')
    releases=json.loads((ROOT/'.state/verified-runtimes.json').read_text())
    for item in releases:
        if item['image']!=proof['image']:raise ValueError('Different verified image')
        item.update(runner_sha256=proof['runner_sha256'],application_proof_sha256=digest(proof_path))
    state_root=ROOT/'.state/real-domain-20260924'
    state_root.mkdir(exist_ok=True)
    catalog=state_root/'runtime.json';catalog.write_text(json.dumps(releases))
    settings=Settings(database_url=f'sqlite:///{state_root}/new.db',storage_root=state_root/'objects',runtime_catalog=catalog)
    store=Store(settings);store.initialize()
    state_path=state_root/'progress.json'
    state=json.loads(state_path.read_text()) if state_path.exists() else {}
    def save():
        temporary=state_path.with_suffix('.partial');temporary.write_text(json.dumps(state,indent=2));temporary.replace(state_path)
    if 'actor' not in state:
        actor=store.create_account('engineering@example.test',secrets.token_urlsafe(32))
        state.update(actor=actor,project=store.create_project(actor,'真实珠三角工程验证；不得解释为正式业务结论'),assets=[],runs={})
        save()
    actor,project=state['actor'],state['project']
    folder=ROOT.parent.parent/'data_quan/zhusanjiao/土地利用'
    sources=sorted(folder.glob('*.tif'))
    assert len(sources)==4
    intake=Intake(store)
    for path in sources:
        if any(a['name']==path.name for a in state['assets']):continue
        with path.open('rb') as source:
            asset=intake.ingest(actor,project,source,path.name)['asset']
        assert asset['sha256']==digest(path)
        state['assets'].append({'id':asset['id'],'name':asset['name'],'sha256':asset['sha256'],'size':asset['size']});save()
        print(json.dumps({'phase':'ingested','file':path.name,'bytes':asset['size']}),flush=True)
    declarations=json.loads((ROOT.parent/'artifacts/runtime/business-intake/user-declarations.json').read_text())
    registry=ModelRegistry(store)
    for purpose,model in [('cluster','ppci_mcdc'),('regression','ppr_ols')]:
        if purpose not in state['runs']:
            task=store.new_task(actor,project,TaskDraft(title='PRD '+purpose+' engineering only',purpose=purpose).model_dump(mode='json'))
            draft=task['draft']
            for index,item in enumerate(state['assets']):
                draft['selection'].append({'asset_id':item['id'],'revision':1,'layer':None})
                draft['mapping'].append({'asset_id':item['id'],'field':'raster/band_1','unit':'m','concept':'provided raster numeric variable; scientific dictionary unconfirmed','support':'grid','role':'response' if purpose=='regression' and index==3 else 'feature'})
            draft['options']={'standardize':True,'size':3 if purpose=='cluster' else 2,'seed':42,'training_scope':'sample','sample_size':1000,'application_scope':'full','validation_intent':'engineering_only','response_basis':'fourth measured raster selected only for technical regression test; not a user-approved scientific response' if purpose=='regression' else None,'user_declarations':declarations}
            task=store.save_task(actor,task['id'],task['revision'],TaskDraft.model_validate(draft).model_dump(mode='json'))
            release=next(r for r in registry.catalog(actor,project) if r['release']['model_id']==model)
            registry.approve(actor,project,model,release['release_digest'])
            job=Execution(store).enqueue(actor,task['id'],task['revision'],'real-domain-v1')
            state['runs'][purpose]={'task_id':task['id'],'job_id':job['id'],'started_at':time.time()};save()
        record=state['runs'][purpose]
        job=Execution(store).read_job(actor,record['job_id'])
        if job['status']=='failed':raise RuntimeError('Existing real computation failed; inspect error before retry: '+str(job['error']))
        if job['status']!='succeeded':
            print(json.dumps({'phase':'full_domain_running','purpose':purpose}),flush=True)
            Worker(store).run_once()
        job=Execution(store).read_job(actor,record['job_id'])
        assert job['status']=='succeeded',job.get('error')
        result=json.loads((settings.storage_root/job['output_key']).read_text())
        record.update(status='PASS',elapsed_seconds=time.time()-record['started_at'],python_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,training=result['data']['training'],application=result['data']['application'],files=result['data']['files'],result_key=job['output_key'],business_validated=False)
        save();print(json.dumps({'phase':'completed','purpose':purpose,'cells':record['application']['predicted_cells'],'seconds':record['elapsed_seconds']}),flush=True)
    (ROOT/'artifacts/real-full-domain-evidence.json').write_text(json.dumps({'scope':'actual 11416x9000 files; explicit engineering-only parameters and response; formal science not validated','assets':state['assets'],'runs':state['runs'],'namespace':str(state_root)},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
