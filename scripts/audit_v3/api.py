"""Actual API/worker and numerical probes against the isolated audit namespace."""
from pathlib import Path
import sys, json, time, copy, hashlib, ast, re, threading
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'next/src'),str(ROOT/'next/vendor')]
import httpx, numpy as np, rasterio
from rasterio.transform import from_origin
OUT=ROOT/'.review/evidence/runs/v3-audit-20260925'
PRIVATE=ROOT/'next/.state/v3-audit-20260925'
access=json.loads((PRIVATE/'settings-access.json').read_text());project=access['project_id']
client=httpx.Client(base_url='http://127.0.0.1:58125',timeout=30)
session=client.post('/api/session',json={'email':access['email'],'password':access['password']});session.raise_for_status()
client.headers['X-CSRF-Token']=session.json()['csrf']
results={'fixture_kind':'engineering_fixture','cases':[],'runs':[],'operators':[],'capability_probe':{},'errors':[]}
def safe(value):
    if isinstance(value,dict):return {k:safe(v) for k,v in value.items() if k not in {'object_key','csrf','password','session','database_url'}}
    if isinstance(value,list):return [safe(x) for x in value]
    if isinstance(value,str):return value.replace(str(ROOT),'<repository>')
    return value
def checkpoint(): (OUT/'api.json').write_text(json.dumps(safe(results),ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def case(name,fn):
    try:
        value=fn();results['cases'].append({'name':name,'status':'PASS','result':safe(value)});print('PASS',name,flush=True);return value
    except Exception as e:
        results['cases'].append({'name':name,'status':'FAIL','error':str(e)[:1800]});print('FAIL',name,flush=True);return None
    finally:checkpoint()
def request(method,path,expected,**kw):
    r=client.request(method,path,**kw)
    assert r.status_code==expected,(path,r.status_code,r.text[:1600])
    return r.json()
def task(kind='assessment',title=None):return request('POST','/api/tasks',201,json={'project_id':project,'task_type':kind,'title':title or '审计-'+kind})
def upload(name):
    with (PRIVATE/'fixtures'/name).open('rb') as f:return request('POST',f'/api/projects/{project}/assets',201,files={'file':(name,f)})['asset']
def bind(t,a,key):return request('POST',f'/api/tasks/{t["id"]}/inputs:attach',200,json={'expected_revision':t['revision'],'idempotency_key':key,'inputs':[{'asset_id':a['id'],'revision':a['revision']}]})
def wait_job(j):
    end=time.monotonic()+45
    while time.monotonic()<end:
        q=request('GET','/api/jobs/'+j['id'],200)
        if q['status'] in ['succeeded','failed','cancelled']:return q
        time.sleep(.1)
    raise AssertionError('Job did not finish in bounded audit window')
def run_indicator(t,code):
    selected=request('POST',f'/api/v1/tasks/{t["id"]}/indicators',200,json={'expected_revision':t['revision'],'idempotency_key':code,'items':[{'indicator_id':code}]})
    current=selected['task'];item=selected['items'][0]
    started=time.monotonic();job=request('POST',f'/api/v1/tasks/{t["id"]}/indicators/{item["selection_id"]}/execute',202,json={'expected_revision':current['revision'],'idempotency_key':code+'-execute'})
    latency=time.monotonic()-started;finished=wait_job(job);assert finished['status']=='succeeded',finished
    result=request('GET',f'/api/jobs/{job["id"]}/result',200)
    result['audit_http_202_seconds']=latency;result['audit_job_id']=job['id']
    r=client.get(f'/api/jobs/{job["id"]}/files/0');assert r.status_code==200
    assert hashlib.sha256(r.content).hexdigest()==result['data']['files'][0]['sha256']
    with rasterio.MemoryFile(r.content) as mem:
        with mem.open() as ds:result['audit_native_values']=ds.read(1,masked=True).filled(np.nan).tolist()
    # JSON null means invalid, not a fabricated numerical zero.
    result['audit_native_values']=[[None if not np.isfinite(v) else v for v in row] for row in result['audit_native_values']]
    results['runs'].append(safe(result));return {'job':job['id'],'status':finished['status'],'http_202_seconds':latency,'values':result['audit_native_values']}

try:
    spec=request('GET','/openapi.json',200)
    results['capability_probe']['actual_paths']=list(spec['paths'])
    # Engineering reflectance is explicitly authored here; never infer physical units for user data.
    with rasterio.open(PRIVATE/'fixtures/spectral-five.tif','w',driver='GTiff',width=3,height=1,count=5,dtype='float64',crs='EPSG:32649',transform=from_origin(400000,2500000,30,30),nodata=-9999) as dst:
        for i,(role,value) in enumerate([('red',.2),('nir',.6),('blue',.1),('green',.3),('swir1',.4)],1):
            dst.write(np.array([[value,0,-9999]]),i);dst.set_band_description(i,role);dst.set_band_unit(i,'1');dst.update_tags(i,common_name=role,physical_quantity='surface_reflectance')
    assets={}
    for name in ['observations.csv','units.zip','units.geojson','spectral-five.tif']:
        a=case('import-'+name,lambda name=name:upload(name))
        if a:assets[name]=a
    t=task();a=assets['observations.csv']
    first=case('input-transaction',lambda:bind(t,a,'audit-attach'))
    case('input-idempotent-replay',lambda: {'same_receipt':bind(t,a,'audit-attach')==first})
    if first:
        current=first['task'];second=bind(current,a,'audit-attach-again');assert second['items'][0]['status']=='already_present'
        results['cases'].append({'name':'duplicate-input-not-rebound','status':'PASS','result':{'status':second['items'][0]['status'],'revision':second['task']['revision']}})
    for kind in ['assessment','simulation','planning','comparison']:
        q=task(kind);check=request('GET',f'/api/tasks/{q["id"]}/preflight',200)
        results['capability_probe'][kind]={'task_id':q['id'],'purpose':q['draft']['purpose'],'task_type':q['draft']['options'].get('task_type'),'preflight':check}
    for code in ['ndvi','evi','savi','ndwi','mndwi','ndbi']:
        t=task(title='真实执行-'+code)
        case('indicator-'+code,lambda t=t,code=code:run_indicator(t,'indicator.'+code))
    # Error envelope probes preserve actual status/code/field paths, never credential bodies.
    t=task()
    for name,method,path,payload in [
        ('invalid-task-field','POST','/api/tasks',{'project_id':project,'title':'','task_type':'assessment'}),
        ('missing-view-fields','PUT',f'/api/tasks/{t["id"]}/view-state',{'expected_revision':0,'state':{}}),
        ('stale-task-revision','PUT',f'/api/tasks/{t["id"]}',{'expected_revision':999,'draft':t['draft']}),
    ]:
        r=client.request(method,path,json=payload);body=r.json();results['errors'].append({'name':name,'path':path,'http_status':r.status_code,'body':safe(body)})
    models=request('GET',f'/api/projects/{project}/models',200)
    results['capability_probe']['model_directory']=models
    model_paths=[p for p in spec['paths'] if 'model' in p]
    results['capability_probe']['model_upload_route_present']=any('upload' in p or 'intake' in p for p in model_paths)
    results['capability_probe']['model_routes']=model_paths
    for feature,term in [('sse','event'),('reproduce','reproduce'),('workflow','workflow'),('checkpoint','checkpoint'),('uncertainty','uncertainty'),('feature_revision','feature-revision')]:
        results['capability_probe'][feature+'_routes']=[p for p in spec['paths'] if term in p]
    from coastmas_next.builtin_operators import BuiltinOperatorRegistry
    registry=BuiltinOperatorRegistry()
    matrix={'labels':['a','b'],'values':[[.1,.2],[.4,.3],[.8,.9]]}
    operator_cases={
        'weight.ahp':{'labels':['a','b','c'],'matrix':[[1,2/3,2/5],[3/2,1,3/5],[5/2,5/3,1]]},
        'weight.manual':{'weights':{'a':.4,'b':.6}},'weight.entropy':matrix,'weight.critic':matrix,
        'reduction.pca':{**matrix,'components':1},
        'classification.fisher_jenks':{'values':[0,.3,.31,.7,.71,1.],'classes':3},
    }
    for code,payload in operator_cases.items():
        value=case('numeric-'+code,lambda code=code,payload=payload:registry.execute(code,payload))
        results['operators'].append({'code':code,'input':payload,'output':value,'execution_scope':'direct real kernel; not an API/UI workflow'})
    for code in ['evaluation.wlc','evaluation.topsis']:
        payload={**matrix,'weight_set':{'kind':'WeightSet','weights':{'a':.4,'b':.6},'profile':'engineering_fixture'}}
        value=case('numeric-'+code,lambda code=code,payload=payload:registry.execute(code,payload))
        results['operators'].append({'code':code,'input':payload,'output':value,'execution_scope':'direct real kernel; not an API/UI workflow'})
    # Inventory is functional trace evidence, not a generated Git diff.
    from coastmas_next.store import metadata
    from coastmas_next.app import create_app
    from coastmas_next.config import Settings
    config=json.loads((PRIVATE/'settings.json').read_text())
    app=create_app(Settings(database_url=config['database_url'],storage_root=Path(config['storage_root'])))
    results['capability_probe']['actual_tables']=sorted(metadata.tables)
    routes=[]
    for r in app.routes:
        if hasattr(r,'endpoint'):
            import inspect
            file=inspect.getsourcefile(r.endpoint)
            routes.append({'path':r.path,'methods':sorted(r.methods or []),'endpoint':r.endpoint.__qualname__,'source':str(Path(file).relative_to(ROOT)) if file and Path(file).is_relative_to(ROOT) else 'framework'})
    (OUT/'routes.json').write_text(json.dumps(routes,indent=2)+'\n')
finally:
    checkpoint();client.close()
