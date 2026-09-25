"""Actual managed local intake through new API; original files stay read-only."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import httpx

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:58010')
    parser.add_argument('--access',type=Path,default=ROOT/'.state/settings-access.json')
    parser.add_argument('--source',type=Path,required=True)
    args=parser.parse_args()
    access=json.loads(args.access.read_text())
    client=httpx.Client(base_url=args.url,timeout=120)
    login=client.post('/api/session',json={'email':access['email'],'password':access['password']});login.raise_for_status()
    client.headers['X-CSRF-Token']=login.json()['csrf']
    project=access['project_id']
    roots=client.get(f'/api/projects/{project}/local-sources');roots.raise_for_status()
    source=next(item for item in roots.json() if item['name']==args.source.name)
    files=[]
    def browse(path=''):
        offset=0
        while True:
            response=client.get(f'/api/projects/{project}/local-sources/{source["id"]}/files',params={'path':path,'offset':offset});response.raise_for_status();page=response.json()
            for item in page['items']:
                if item['directory']:
                    if not item['path'].startswith('model'):browse(item['path'])
                elif item['name'].lower().endswith(('.tif','.tiff')):files.append(item)
            offset+=page['limit']
            if offset>=page['total']:break
    browse()
    assert len(files)==40, {'actual_tiff_count':len(files)}
    state_path=ROOT/'.state/real-batch-progress.json'
    if state_path.exists():
        state=json.loads(state_path.read_text())
        assert state['project']==project
    else:
        task=client.post('/api/tasks',json={'project_id':project,'title':'真实业务40幅栅格接入验收（非正式科学结论）','purpose':'inspect'});task.raise_for_status()
        response=client.post(f'/api/projects/{project}/imports',json={'task_id':task.json()['id'],'idempotency_key':'real-40-tiff-v1','items':[{'name':item['name'],'size':item['size'],'path':item['path'],'source_id':source['id']} for item in files]});response.raise_for_status()
        state={'project':project,'task_id':task.json()['id'],'batch_id':response.json()['id']}
        state_path.write_text(json.dumps(state))
    deadline=time.monotonic()+600
    while True:
        response=client.get(f'/api/imports/{state["batch_id"]}');response.raise_for_status();batch=response.json()
        counts={status:sum(item['status']==status for item in batch['items']) for status in ['ready','failed','queued','receiving']}
        if counts['ready']+counts['failed']==40:break
        if time.monotonic()>deadline:raise TimeoutError(counts)
        time.sleep(2)
    records=[]
    for item in batch['items']:
        assert item['status']=='ready', {'name':item['source']['name'],'error':item['error']}
        response=client.get(f'/api/assets/{item["asset_id"]}');response.raise_for_status();asset=response.json()
        path=args.source/item['source']['path']
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            while chunk:=stream.read(1024**2):digest.update(chunk)
        assert asset['sha256']==digest.hexdigest()
        assert asset['size']==path.stat().st_size
        records.append({'source':item['source']['path'],'asset_id':asset['id'],'bytes':asset['size'],'sha256':asset['sha256'],'profile':asset['facts']['profile'],'technical_issues':asset['facts']['issues']})
    task=client.get(f'/api/tasks/{state["task_id"]}').json()
    assert len(task['draft']['selection'])==40
    proof={'status':'PASS','scope':'all 40 original TIFF bytes managed through authorized local batch API; technical intake only, not scientific approval','task_url':args.url+'/tasks/'+state['task_id'],'batch_id':state['batch_id'],'assets':records,'count':len(records),'bytes':sum(item['bytes'] for item in records),'originals':'read only','scientific_values_invented':False}
    (ROOT/'artifacts/real-40-tiff-intake.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2))
    print(json.dumps({k:proof[k] for k in ['status','count','bytes','task_url']}))

if __name__=='__main__':main()
