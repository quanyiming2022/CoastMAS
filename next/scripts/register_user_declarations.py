"""Register existing explicit user statements against freshly imported real byte identities."""
import hashlib
import json
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1]
access=json.loads((ROOT/'.state/settings-access.json').read_text())
original=ROOT.parent/'artifacts/runtime/business-intake/user-declarations.json'
claims=json.loads(original.read_text())
proof=json.loads((ROOT/'artifacts/real-40-tiff-intake.json').read_text())
state_path=ROOT/'.state/real-declarations-progress.json'
client=httpx.Client(base_url='http://127.0.0.1:58010',timeout=120)
r=client.post('/api/session',json={'email':access['email'],'password':access['password']});r.raise_for_status();client.headers['X-CSRF-Token']=r.json()['csrf']
project=access['project_id'];task_id=proof['task_url'].rsplit('/',1)[1]
state=json.loads(state_path.read_text()) if state_path.exists() else {}
source_sha=hashlib.sha256(original.read_bytes()).hexdigest()
basis='用户在本次研发对话中明确提供的声明；原记录 SHA256 '+source_sha+'。来源网址与许可原文尚待补充；不是文件元数据，也不是正式业务有效性认证。'
if 'statement' not in state:
    r=client.get('/api/tasks/'+task_id);r.raise_for_status();task=r.json()
    task['draft']['options']['source_statement']={'basis':basis,'source_description':claims['source'],'license_statement':claims['use_restriction'],'observed_year':claims['year']}
    r=client.put('/api/tasks/'+task_id,json={'expected_revision':task['revision'],'draft':task['draft']});r.raise_for_status();saved=r.json()
    r=client.post('/api/tasks/'+task_id+'/publish-statement',json={'expected_revision':saved['revision'],'approve':True});r.raise_for_status()
    state['statement']={'id':r.json()['template']['id'],'revision':r.json()['template']['revision']};state_path.write_text(json.dumps(state))
if 'distance_units' not in state:
    subset=[asset for asset in proof['assets'] if asset['source'].startswith('zhusanjiao/')]
    assert len(subset)==4 and claims['units']['zhusanjiao/']=='m'
    r=client.post(f'/api/projects/{project}/templates',json={'title':'原批次珠三角距离单位：米','purpose':'semantic','profiles':['geotiff','cog'],'basis':basis,'scope':{'asset_sha256':[asset['sha256'] for asset in subset]},'rules':[{'field':'raster/band_1','unit':'m'}]});r.raise_for_status();template=r.json()
    r=client.post('/api/templates/'+template['id']+'/approve',json={'revision':template['revision']});r.raise_for_status()
    state['distance_units']={'id':template['id'],'revision':template['revision']};state_path.write_text(json.dumps(state))
r=client.get('/api/tasks/'+task_id);r.raise_for_status();task=r.json()
r=client.post('/api/tasks/'+task_id+'/sources',json={'expected_revision':task['revision'],'assets':[asset['asset_id'] for asset in proof['assets']]});r.raise_for_status();task=r.json()
assert len(task['draft']['options']['inherited_declarations'])==40
assert all(value['observed_year']==2022 for value in task['draft']['options']['inherited_declarations'].values())
assert sum(binding['unit']=='m' for binding in task['draft']['mapping'])==4
assert all(binding['concept'] is None for binding in task['draft']['mapping'])
report={'status':'PASS','scope':'register explicit existing user statements in isolated new project; not a license or scientific-validity certification','task_url':proof['task_url'],'declaration_record_sha256':source_sha,'templates':state,'file_scoped_source_statements':40,'unit_bindings_m':4,'unknown_indicator_meanings_preserved':True,'year_precision':'year only, no dates synthesized','license_verified':False}
(ROOT/'artifacts/real-source-declarations.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({key:report[key] for key in ['status','file_scoped_source_statements','unit_bindings_m','unknown_indicator_meanings_preserved']}))
