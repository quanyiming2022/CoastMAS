"""Isolated engineering evidence on complete real source grids; no business conclusion."""
import hashlib
import json
import argparse
import time
from pathlib import Path

import httpx
import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build',required=True)
parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args()
EVIDENCE=args.output.resolve()
EVIDENCE.mkdir(parents=True,exist_ok=True)
access = json.loads((ROOT / '.state/unified-business-20260924/settings-access.json').read_text())
entry = json.loads((ROOT / 'artifacts/unified-business-20260924/browser7/real-source-snapshot.json').read_text())
settings = json.loads((ROOT / '.state/unified-business-20260924/settings.json').read_text())
assert Path(settings['web_root']).name == args.build
objects = Path(settings['storage_root'])
source = Path('/Users/quanyiming/Projects/data_quan') / entry['source_relative']
project = entry['project']
with httpx.Client(base_url='http://127.0.0.1:58013', timeout=120) as client:
    def request(method, path, **kwargs):
        response = client.request(method, '/api' + path, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(f'{path}: {response.status_code} {response.text[:400]}')
        return response.json()
    login = request('POST','/session',json={'email':access['email'],'password':access['password']})
    client.headers['X-CSRF-Token'] = login['csrf']
    definition = {'title':'全域数值保持工程验证（非正式评价）','purpose':'method','basis':
        '工程验收固定算式u=x/1000000，权重1。m来自用户已给的珠三角距离声明；方向和参照仅为工程对照，不宣称业务适用。',
        'profiles':['geotiff'], 'configuration':{'task':'assessment','method':'weighted','indicators':[
            {'concept':'原始距水体距离的工程对照','unit':'m','lower':0.,'upper':1000000.,'positive':True,'weight':1.}]}}
    workspace = request('POST',f'/projects/{project}/method-workspaces',json={'definition':definition})
    method = request('POST',f"/method-workspaces/{workspace['id']}/publish",json={'expected_revision':1,'approve':True})['template']
    task = request('POST','/tasks',json={'project_id':project,'goal':'comprehensive-assessment','title':'全域原值—评分—贡献—综合工程验收'})
    task = request('POST',f"/tasks/{task['id']}/inputs:attach",json={'expected_revision':1,'idempotency_key':'original', 'inputs':[{'asset_id':entry['asset_id'],'revision':1}]})['task']
    task = request('POST',f"/tasks/{task['id']}/apply-method",json={'expected_revision':task['revision'],'method_id':method['id'],'method_revision':1})
    draft = task['draft']; draft['mapping']=[{'asset_id':entry['asset_id'],'field':'raster/band_1','concept':'原始距水体距离的工程对照','unit':'m','role':'feature','support':'cell'}]
    draft['options']['engineering_verification']='API-configured fixed numerical benchmark; not a least-input user measurement or formal ecological assessment.'
    task = request('PUT',f"/tasks/{task['id']}",json={'expected_revision':task['revision'],'draft':draft})
    preflight=request('GET',f"/tasks/{task['id']}/preflight");assert preflight['ready'],preflight
    job=request('POST',f"/tasks/{task['id']}/execute",json={'expected_revision':task['revision'],'idempotency_key':'full-domain'})
    (EVIDENCE/'full-grid-inflight.json').write_text(json.dumps({'task':task['id'],'job':job['id'],'project':project}))
    print('Submitted real full-grid job; independent comparison follows.',flush=True)
    deadline=time.monotonic()+1200
    while job['status'] in {'queued','running'}:
        if time.monotonic()>deadline:raise TimeoutError('Worker still running; inspect recorded job, do not resubmit')
        time.sleep(1);job=request('GET',f"/jobs/{job['id']}")
    assert job['status']=='succeeded',job.get('error')
    result=request('GET',f"/jobs/{job['id']}/result")
    files={item['role']:item for item in result['data']['files']}
    assert set(files)=={'raw_indicator','indicator','contribution','composite','quality'}
    assert result['states']['business_validated'] is False
    from contextlib import ExitStack
    with ExitStack() as stack:
        original=stack.enter_context(rasterio.open(source));outputs={role:stack.enter_context(rasterio.open(objects/item['key'])) for role,item in files.items()}
        for output in outputs.values():assert (output.crs,output.transform,output.width,output.height)==(original.crs,original.transform,original.width,original.height)
        count,total,max_error=0,0,0.
        for _,window in original.block_windows(1):
            raw=original.read(1,window=window,masked=True);valid=~np.ma.getmaskarray(raw)&np.isfinite(raw.data)
            count+=int(valid.sum());total+=valid.size
            for role in ['raw_indicator','indicator','contribution','composite']:
                actual=outputs[role].read(1,window=window,masked=True)
                assert np.array_equal(~np.ma.getmaskarray(actual),valid),role
                expected=raw.data[valid] if role=='raw_indicator' else raw.data[valid].astype('float64')/1000000.
                if expected.size:
                    error=float(np.max(np.abs(actual.data[valid]-expected)));max_error=max(max_error,error);assert error<1e-14,(role,error)
            assert np.array_equal(outputs['quality'].read(1,window=window),valid.astype('uint8'))
        assert outputs['raw_indicator'].units==('m',)
    with source.open('rb') as stream:source_hash=hashlib.file_digest(stream,'sha256').hexdigest()
    assert source_hash==entry['sha256']
    report={'build':args.build,'project':project,'task_id':task['id'],'job_id':job['id'],'draft_revision':task['revision'],'asset_id':entry['asset_id'],'source_sha256':source_hash,'total_pixels':total,'valid_pixels':count,'mask_mismatches':0,'maximum_absolute_error':max_error,'full_domain':True,'outputs':list(files.values()),'business_validated':False,'scope':'Engineering numerical verification on actual source; no claim of formal coastal evaluation or independent predictive accuracy.'}
    (EVIDENCE/'full-grid.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'total_pixels':total,'valid_pixels':count,'outputs':len(files),'max_error':max_error}),flush=True)
