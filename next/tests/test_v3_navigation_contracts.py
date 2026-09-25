import pytest

@pytest.mark.parametrize('task_type,purpose', [('assessment','assessment'),('simulation','simulation'),('planning','optimization'),('comparison','comparison')])
def test_four_task_types_persist_without_starting_work(workspace,task_type,purpose):
    _,_,client,project=workspace
    response=client.post('/api/tasks',json={'project_id':project,'title':'V3 task','task_type':task_type})
    assert response.status_code==201,response.text
    task=response.json()
    assert task['draft']['purpose']==purpose
    assert task['draft']['options']['task_type']==task_type
    assert client.get('/api/tasks/'+task['id']).json()==task
    if task_type=='simulation':
        submitted=client.post('/api/tasks/'+task['id']+'/execute',json={'expected_revision':task['revision'],'idempotency_key':'unavailable-is-not-executable'})
        assert submitted.status_code==422

def test_indicator_library_reads_project_without_creating_a_task(workspace):
    _,_,client,project=workspace
    before=client.get(f'/api/projects/{project}/tasks').json()
    response=client.get(f'/api/v1/projects/{project}/indicators')
    assert response.status_code==200,response.text
    assert any(x['indicator_id']=='indicator.ndvi' for x in response.json()['items'])
    assert client.get(f'/api/projects/{project}/tasks').json()==before
    assert client.get('/api/v1/projects/inaccessible/indicators').status_code in {403,404}
