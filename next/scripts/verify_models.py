"""New API -> approved release -> durable worker -> original R -> real download."""
import csv
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import numpy as np
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')]
from coastmas_next.app import create_app
from coastmas_next.config import Settings
from coastmas_next.store import Store
from coastmas_next.worker import Worker


def main():
    catalog=ROOT/'.state/verified-runtimes.json'
    image=json.loads(catalog.read_text())[0]['image']
    raw=subprocess.check_output(['docker','run','--rm','--network','none','--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--memory','1g',image,'Rscript','--vanilla','-e','write.csv(iris[,1:4],stdout(),row.names=FALSE)'],timeout=45,text=True)
    proof=json.loads((ROOT/'artifacts/provided-model-new-proof.json').read_text())
    records=[]
    with tempfile.TemporaryDirectory(prefix='coastmas-next-model-e2e-') as temporary:
        folder=Path(temporary)
        settings=Settings(database_url=f'sqlite:///{folder}/new.db',storage_root=folder/'objects',runtime_catalog=catalog)
        store=Store(settings);store.initialize()
        actor=store.create_account('analyst@example.test','isolated-test-password')
        project=store.create_project(actor,'New model contract verification')
        client=TestClient(create_app(settings))
        login=client.post('/api/session',json={'email':'analyst@example.test','password':'isolated-test-password'}).json()
        client.headers['X-CSRF-Token']=login['csrf']
        for purpose,model in [('cluster','ppci_mcdc'),('regression','ppr_ols')]:
            task=client.post('/api/tasks',json={'project_id':project,'title':'Original R new API verification','purpose':purpose}).json()
            response=client.post(f'/api/projects/{project}/assets',files={'file':('iris-technical-fixture.csv',raw.encode())},data={'task_id':task['id'],'expected_revision':'1'})
            assert response.status_code==201,response.text
            task=response.json()['task']
            draft=task['draft']
            for i,mapping in enumerate(draft['mapping']):
                mapping.update(unit='cm',concept=['sepal length','sepal width','petal length','petal width'][i],support='point',role='response' if purpose=='regression' and i==0 else 'feature')
            draft['options'].update(standardize=False,size=3 if purpose=='cluster' else 2,seed=42)
            task=client.put(f"/api/tasks/{task['id']}",json={'expected_revision':task['revision'],'draft':draft}).json()
            blocked=client.get(f"/api/tasks/{task['id']}/preflight").json()
            assert not blocked['ready']
            release=next(r for r in client.get(f'/api/projects/{project}/models').json() if r['release']['model_id']==model)
            assert not release['approved']
            approval=client.post(f'/api/projects/{project}/models/{model}/approve',json={'release_digest':release['release_digest']})
            assert approval.status_code==200,approval.text
            run=client.post(f"/api/tasks/{task['id']}/execute",json={'expected_revision':task['revision'],'idempotency_key':model})
            assert run.status_code==202,run.text
            job=run.json();assert Worker(store).run_once()
            complete=client.get(f"/api/jobs/{job['id']}").json()
            assert complete['status']=='succeeded',complete
            output=client.get(f"/api/jobs/{job['id']}/download").json()
            assert output['manifest']['runtime']['release_digest']==release['release_digest']
            assert output['states']['business_validated'] is False
            result=output['data']
            if purpose=='cluster':
                actual=np.asarray(result['cluster']);expected=np.asarray(proof['clustering']['result']['cluster'])
                assert np.array_equal(actual[:,None]==actual,expected[:,None]==expected)
                measure={'pair_disagreements':0}
            else:
                error=float(np.max(np.abs(np.asarray(result['fitted'])-np.asarray(proof['regression']['result']['fitted']))))
                assert error<=1e-12,error
                measure={'max_abs_error':error}
            filename='new-'+model+'-result.json'
            (ROOT/'artifacts'/filename).write_text(json.dumps(output,ensure_ascii=False,indent=2))
            records.append({'model':model,'status':'PASS','rows':len(result['row_ids']),'before_approval':'BLOCKED','artifact':filename,**measure})
    (ROOT/'artifacts/new-model-api-evidence.json').write_text(json.dumps({'scope':'new independent API/DB/queue and original supplied algorithms; technical iris fixture, not coastal validity','models':records},indent=2))
    print(json.dumps(records))

if __name__=='__main__':main()
