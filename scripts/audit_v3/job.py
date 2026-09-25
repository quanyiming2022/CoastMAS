from pathlib import Path
import httpx,json,time,hashlib
import rasterio,numpy as np
from rasterio.transform import from_origin
R=Path(__file__).resolve().parents[2];P=R/'next/.state/v3-audit-20260925';O=R/'.review/evidence/runs/v3-audit-20260925';a=json.loads((P/'settings-access.json').read_text());c=httpx.Client(base_url='http://127.0.0.1:58125',timeout=20);r=c.post('/api/session',json={'email':a['email'],'password':a['password']});r.raise_for_status();c.headers['X-CSRF-Token']=r.json()['csrf'];out={'fixture':'engineering_fixture','events':[]}
def request(m,p,expected=200,**kw):
 r=c.request(m,p,**kw);assert r.status_code==expected,(p,r.status_code,r.text[:1000]);return r.json()
try:
 p=request('POST','/api/projects',201,json={'name':'异步取消工程审计'})['id'];f=P/'fixtures/cancel-mask.tif'
 with rasterio.open(f,'w',driver='GTiff',width=8192,height=8192,count=1,dtype='uint8',crs='EPSG:32649',transform=from_origin(400000,2500000,10,10),compress='deflate',tiled=True) as ds:
  block=np.ones((1024,8192),dtype='uint8')
  for y in range(0,8192,1024):ds.write(block,1,window=rasterio.windows.Window(0,y,8192,1024))
 with f.open('rb')as s:asset=request('POST',f'/api/projects/{p}/assets',201,files={'file':('cancel-mask.tif',s)})['asset']
 t=request('POST','/api/tasks',201,json={'project_id':p,'task_type':'assessment','title':'取消实际空间处理'})
 t=request('POST',f'/api/tasks/{t["id"]}/inputs:attach',json={'expected_revision':t['revision'],'idempotency_key':'attach','inputs':[{'asset_id':asset['id'],'revision':asset['revision']}]})['task']
 n=request('POST',f'/api/tasks/{t["id"]}/processing-nodes',201,json={'expected_revision':t['revision'],'operator':'valid_mask','idempotency_key':'audit-node','asset_id':asset['id'],'band':1,'parameters':{}})
 start=time.monotonic();j=request('POST',f'/api/processing-nodes/{n["id"]}/execute',202,json={'expected_revision':t['revision'],'idempotency_key':'audit-cancel'});out['http_202_seconds']=time.monotonic()-start
 for i in range(200):
  q=request('GET','/api/jobs/'+j['id']);out['events'].append({k:q.get(k) for k in ['status','cancel_requested','started','finished']})
  if q['status']=='running':break
  if q['status'] in ('failed','succeeded','cancelled'):raise AssertionError('finished before running cancellation could be tested')
  time.sleep(.02)
 cancel=request('POST',f'/api/jobs/{j["id"]}/cancel');out['cancel_ack']={k:cancel.get(k)for k in ['status','cancel_requested','output_key']}
 for i in range(200):
  q=request('GET','/api/jobs/'+j['id']);out['events'].append({k:q.get(k)for k in ['status','cancel_requested','started','finished']})
  if q['status'] in ('failed','succeeded','cancelled'):break
  time.sleep(.02)
 out['final']={k:q.get(k)for k in ['status','cancel_requested','output_key']};out['result_http']=c.get(f'/api/jobs/{j["id"]}/result').status_code;assert q['status']=='cancelled' and q['output_key'] is None
 out['status']='PASS';out['meaning']='Actual running worker acknowledged cancellation; legacy boolean/status contract differs from new unified FSM.'
except Exception as e:out['status']='FAIL';out['error']=repr(e)
finally:(O/'job-cancel-corrected.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));c.close();print(out['status'],out.get('error',''))
