"""Supplement isolated HTTP probes; never touches live records or original source data."""
from pathlib import Path
import json,time,hashlib,sys,secrets
import httpx,numpy as np,rasterio
from rasterio.transform import from_origin
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'next/.state/v3-audit-20260925';O=ROOT/'.review/evidence/runs/v3-audit-20260925';N=ROOT/'.review/evidence/numerical/v3-audit-20260925';N.mkdir(parents=True,exist_ok=True)
a=json.loads((P/'settings-access.json').read_text());c=httpx.Client(base_url='http://127.0.0.1:58125',timeout=25);s=c.post('/api/session',json={'email':a['email'],'password':a['password']});s.raise_for_status();c.headers['X-CSRF-Token']=s.json()['csrf'];out={'cases':[],'runs':[],'matching':[],'errors':[]}
def safe(x):
 if isinstance(x,dict):return {k:safe(v) for k,v in x.items() if k not in {'password','csrf','object_key','output_key','key','storage_root'}}
 if isinstance(x,list):return [safe(v) for v in x]
 if isinstance(x,str):return x.replace(str(ROOT),'<repository>')
 return x
def save(): (O/'followup-corrected.json').write_text(json.dumps(safe(out),ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def req(m,p,e=200,**kw):
 r=c.request(m,p,**kw);assert r.status_code==e,(p,r.status_code,r.text[:1000]);return r.json()
def case(name,fn):
 try: out['cases'].append({'name':name,'status':'PASS','detail':fn()});print('PASS',name,flush=True)
 except Exception as e:out['cases'].append({'name':name,'status':'FAIL','error':repr(e)});print('FAIL',name,repr(e)[:300],flush=True)
 finally:save()
def project(name):return req('POST','/api/projects',201,json={'name':'审计夹具-'+name})['id']
def task(p,title):return req('POST','/api/tasks',201,json={'project_id':p,'task_type':'assessment','title':title})
def upload(p,f):
 with f.open('rb') as v:return req('POST',f'/api/projects/{p}/assets',201,files={'file':(f.name,v)})['asset']
def catalog(t,code='indicator.ndvi'):return next(x for x in req('GET',f'/api/v1/tasks/{t["id"]}/indicators')['items'] if x['indicator_id']==code)
def recover():
 ts=req('GET',f'/api/management/catalog/tasks?project={a["project_id"]}&query=真实执行-&limit=100')['items'];assert len(ts)==6
 expected={'ndvi':.5,'evi':2.5*(.6-.2)/(.6+6*.2-7.5*.1+1),'savi':1.5*(.6-.2)/(.6+.2+.5),'ndwi':(.3-.6)/(.3+.6),'mndwi':(.3-.4)/(.3+.4),'ndbi':(.4-.6)/(.4+.6)}
 for t in ts:
  j=req('GET',f'/api/tasks/{t["id"]}/jobs')['items'][0];r=req('GET',f'/api/jobs/{j["id"]}/result');d=req('GET',f'/api/jobs/{j["id"]}/descriptor');name=t['name'].replace('真实执行-','');broken=c.get(f'/api/jobs/{j["id"]}/files/0');valid=c.get(f'/api/jobs/{j["id"]}/artifacts/0/download');assert valid.status_code==200,valid.text
  sha=hashlib.sha256(valid.content).hexdigest();assert sha==r['data']['files'][0]['sha256'];(N/(name+'.tif')).write_bytes(valid.content)
  with rasterio.MemoryFile(valid.content) as f:
   with f.open() as ds:v=ds.read(1,masked=True);values=[[None if np.ma.is_masked(x) else float(x) for x in row] for row in v];assert np.isclose(v[0,0],expected[name],rtol=1e-12,atol=1e-12)
  row={'task':t['id'],'job':j['id'],'name':name,'status':j['status'],'native_values':values,'expected_first_pixel':expected[name],'numerical_check':'PASS','sha256':sha,'ui_download_status':broken.status_code,'ui_download_response':broken.text[:100],'alternate_download_status':valid.status_code,'manifest':safe(r['manifest']),'data':safe(r['data']),'descriptor':safe(d)};out['runs'].append(row)
 return {'runs':len(ts),'actual_numeric_pass':6,'ui_download_fail':6}
case('recover-six-real-artifacts',recover)
def matchcase(name,files,code,expected):
 p=project(name)
 for f in files:upload(p,f)
 t=task(p,name);item=catalog(t,code);out['matching'].append({'name':name,'task':t['id'],'catalog_item':item});assert item['status']==expected,item;return {'status':item['status'],'missing':item.get('missing'),'diagnostics':item.get('diagnostics')}
case('matcher-ready',lambda:matchcase('可直接匹配',[P/'fixtures/spectral-five.tif'],'indicator.ndvi','ready'))
case('matcher-missing-NIR',lambda:matchcase('缺NIR',[P/'fixtures/red-only.tif'],'indicator.ndvi','missing'))
case('matcher-hard-conflict',lambda:matchcase('不确认物理量',[P/'fixtures/red-nir.tif'],'indicator.ndvi','inapplicable'))
for year,x in [(2020,400000),(2025,400005)]:
 f=P/f'fixtures/land-{year}.tif'
 with rasterio.open(f,'w',driver='GTiff',width=2,height=1,count=1,dtype='uint8',crs='EPSG:6933',transform=from_origin(x,2500000,10,10)) as ds:ds.write(np.array([[1,2]],dtype='uint8'),1);ds.update_tags(observed_year=str(year),built_up_codes='[2]')
case('matcher-legal-adaptation',lambda:matchcase('需适配',[P/'fixtures/land-2020.tif',P/'fixtures/land-2025.tif'],'indicator.urban_speed','adaptation'))
def security():
 credentials=[]; accounts=[]
 for admin in [False,True]:
  email=('audit-outsider-admin-' if admin else 'audit-viewer-')+secrets.token_hex(4)+'@example.test';pw=secrets.token_urlsafe(25);account=req('POST','/api/accounts',201,json={'email':email,'password':pw,'system_admin':admin});v=httpx.Client(base_url=c.base_url);login=v.post('/api/session',json={'email':email,'password':pw});login.raise_for_status();v.headers['X-CSRF-Token']=login.json()['csrf'];credentials.append({'email':email,'password':pw,'admin':admin,'id':account['id']});accounts.append((v,account))
 p=project('授权边界');t=task(p,'权限夹具');viewer,viewer_account=accounts[0];other,_=accounts[1]
 before=other.get('/api/tasks/'+t['id']);assert before.status_code in (403,404),(before.status_code,before.text)
 req('PUT',f'/api/projects/{p}/members/{viewer_account["id"]}',json={'role':'viewer'})
 allow=viewer.get('/api/tasks/'+t['id']);deny=viewer.put('/api/tasks/'+t['id'],json={'expected_revision':1,'draft':t['draft']});global_deny=viewer.get('/api/accounts');assert [allow.status_code,deny.status_code,global_deny.status_code]==[200,403,403]
 req('DELETE',f'/api/projects/{p}/members/{viewer_account["id"]}',200);revoked=viewer.get('/api/tasks/'+t['id']);assert revoked.status_code in (403,404)
 (P/'audit-roles.json').write_text(json.dumps({'accounts':credentials,'project':p,'task':t['id']}));(P/'audit-roles.json').chmod(0o600)
 return {'outsider_system_admin_read':before.status_code,'viewer_read':allow.status_code,'viewer_write':deny.status_code,'viewer_account_directory':global_deny.status_code,'removed_member_read':revoked.status_code}
case('live-api-project-permissions',security)
try:
 live=c.get('http://127.0.0.1:58013/',timeout=8);iso=c.get('/');out['baseline_same_index']={'live_status':live.status_code,'isolated_status':iso.status_code,'live_sha256':hashlib.sha256(live.content).hexdigest(),'isolated_sha256':hashlib.sha256(iso.content).hexdigest(),'same':live.content==iso.content}
except Exception as e:out['baseline_error']=repr(e)
save();c.close()
