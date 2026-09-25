import {test,expect} from '@playwright/test';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {createReadStream} from 'node:fs';
import {evidenceDirectory,evidencePath} from './evidence';

test('U63–U65 fixed full-grid raster and nonspatial CSV results with historical switching',async({page})=>{
  test.setTimeout(240000);
  if(!process.env.COASTMAS_NEXT_TEST_URL?.endsWith(':58013'))throw new Error('Isolated only');
  const source=JSON.parse(await readFile(process.env.COASTMAS_NEXT_FULL_GRID_EVIDENCE!,'utf8'));
  const access=JSON.parse(await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE!,'utf8'));
  await mkdir(evidenceDirectory,{recursive:true});await page.setViewportSize({width:1440,height:900});
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/results?project='+source.project);await page.getByLabel('邮箱',{exact:true}).fill(access.email);await page.getByLabel('密码',{exact:true}).fill(access.password);await page.getByRole('button',{name:'登录',exact:true}).click();await expect(page.getByRole('button',{name:'新建研究',exact:true})).toBeVisible();
  const session=await(await page.request.get('/api/session')).json(),headers={'X-CSRF-Token':session.csrf};
  const originalTask=await(await page.request.get('/api/tasks/'+source.task_id)).json();
  const region=page.locator('.research-result'),inspector=page.getByRole('complementary',{name:'研究共用右侧面板'});
  async function open(query:string){await page.getByRole('link',{name:'成果管理',exact:true}).click();const catalog=page.getByRole('region',{name:'成果管理',exact:true});await catalog.getByLabel('搜索成果管理',{exact:true}).fill(query);await catalog.getByLabel('搜索成果管理',{exact:true}).press('Enter');await catalog.getByRole('button',{name:'查看成果',exact:true}).first().click();}
  async function downloadLink(id:string,index='0'){await region.getByRole('button',{name:'导出',exact:true}).click();await expect(region.getByRole('link',{name:'下载实际成果',exact:true})).toHaveAttribute('href',`/api/jobs/${id}/artifacts/${index}/download`);await region.getByRole('button',{name:'导出',exact:true}).click();}
  await open(originalTask.draft.title);
  await expect(region.getByRole('region',{name:'资料地图',exact:true})).toBeVisible();await expect(region.getByRole('status',{name:'图层就绪',exact:true})).toBeVisible({timeout:90000});
  const descriptor=await(await page.request.get(`/api/jobs/${source.job_id}/descriptor`)).json();expect(descriptor.primary.role).toBe('composite');expect(descriptor.outputs).toHaveLength(5);expect(descriptor.primary.sha256).toBe(source.outputs[0].sha256);
  const measurements=[];
  for(const [width,height] of [[1440,900],[1366,768]]){await page.setViewportSize({width:width!,height:height!});const box=await region.getByRole('region',{name:'资料地图',exact:true}).boundingBox();expect(box).not.toBeNull();expect(box!.y).toBeLessThanOrEqual(160);if(height===900)expect(box!.height).toBeGreaterThanOrEqual(650);expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width!+1);measurements.push({width,height,map:box});await page.screenshot({path:evidencePath(`full-grid-composite-${width}.png`)});}
  await page.setViewportSize({width:1440,height:900});
  for(const index of ['1','2','3','4','0']){await region.getByLabel('成果图层',{exact:true}).selectOption(index);await page.getByRole('complementary',{name:'研究内容管理器'}).getByRole('checkbox',{name:/^显示 /}).nth(Number(index)).check();await expect(region.getByRole('status',{name:'图层就绪',exact:true})).toBeVisible({timeout:90000});await downloadLink(source.job_id,index);}
  const inspection=page.waitForResponse(r=>r.url().includes(`/jobs/${source.job_id}/artifacts/0/inspect`)&&r.request().method()==='POST');await region.getByRole('region',{name:'资料地图',exact:true}).click({position:{x:240,y:180}});const pixel=await(await inspection).json();expect(pixel.sha256).toBe(source.outputs[0].sha256);await expect(inspector.getByLabel('点查结果',{exact:true})).toBeVisible();
  await region.getByRole('button',{name:'样式',exact:true}).click();await inspector.getByRole('slider',{name:'不透明度',exact:true}).fill('0.6');await expect(page.locator('.research-save-status')).toHaveText('已保存');await region.getByRole('button',{name:'样式',exact:true}).click();
  await region.getByRole('button',{name:'详情',exact:true}).click();await inspector.getByText('查看实际统计表',{exact:true}).click();await expect(inspector.getByRole('table',{name:'成果全域分布',exact:true})).toBeVisible();
  await region.getByRole('button',{name:'导出',exact:true}).click();const downloaded=page.waitForEvent('download');await region.getByRole('link',{name:'下载实际成果',exact:true}).click();const path=await(await downloaded).path();const h=createHash('sha256');for await(const chunk of createReadStream(path!))h.update(chunk);expect(h.digest('hex')).toBe(source.outputs[0].sha256);await region.getByRole('button',{name:'导出',exact:true}).click();
  const editor=await(await page.request.post(`/api/projects/${source.project}/method-workspaces`,{headers,data:{definition:{title:'CSV数值独立基准',purpose:'method',profiles:['csv'],basis:'工程数学基准，不是实际生态评级',configuration:{task:'assessment',method:'weighted',indicators:['a','b','c'].map((concept,i)=>({concept,unit:'1',lower:0,upper:1,positive:true,weight:[.2,.3,.5][i]}))}}}})).json();
  const method=await(await page.request.post(`/api/method-workspaces/${editor.id}/publish`,{headers,data:{expected_revision:1,approve:true}})).json();expect(method.template).toBeTruthy();
  const csv=await(await page.request.post(`/api/projects/${source.project}/assets`,{headers,multipart:{file:{name:'numeric-proof.csv',mimeType:'text/csv',buffer:Buffer.from('id,a,b,c\n001,0.4,0.6,0.8\n002,0.2,0.3,0.4\n')}}})).json();
  const task=await(await page.request.post('/api/tasks',{headers,data:{project_id:source.project,goal:'comprehensive-assessment',title:'无空间CSV '+Date.now()}})).json();
  const draft={...task.draft,selection:[{asset_id:csv.asset.id,revision:1}],mapping:[{asset_id:csv.asset.id,field:'table/id',role:'identity'},...['a','b','c'].map(concept=>({asset_id:csv.asset.id,field:'table/'+concept,role:'feature',unit:'1',concept,support:'point'}))],method_id:method.template.id,options:{...task.draft.options,method_revision:1}};
  expect((await page.request.put(`/api/tasks/${task.id}`,{headers,data:{expected_revision:1,draft}})).ok()).toBe(true);
  const submitted=await page.request.post(`/api/tasks/${task.id}/execute`,{headers,data:{expected_revision:2,idempotency_key:'numeric-proof'}});expect(submitted.status()).toBe(202);const job=await submitted.json();
  await expect.poll(async()=>(await(await page.request.get(`/api/jobs/${job.id}`)).json()).status,{timeout:30000}).toBe('succeeded');
  const numeric=await(await page.request.get(`/api/jobs/${job.id}/result`)).json();expect(numeric.data.scores).toEqual([expect.closeTo(.66,12),expect.closeTo(.33,12)]);
  await open(task.draft.title);await expect(region.getByRole('table',{name:'观测结果',exact:true})).toContainText('0.6600000');await expect(region.getByRole('region',{name:'资料地图',exact:true})).toHaveCount(0);await page.screenshot({path:evidencePath('nonspatial-csv-table.png')});
  await open(originalTask.draft.title);await expect(region.getByRole('region',{name:'资料地图',exact:true})).toBeVisible();await expect(region.getByRole('table',{name:'观测结果',exact:true})).toHaveCount(0);await downloadLink(source.job_id);await page.reload();await expect(region.getByRole('status',{name:'图层就绪',exact:true})).toBeVisible({timeout:90000});await downloadLink(source.job_id);
  expect(await(await page.request.get('/api/tasks/'+source.task_id)).json()).toEqual(originalTask);expect(errors).toEqual([]);
  await writeFile(evidencePath('results-verification.json'),JSON.stringify({project:source.project,spatial_run:source.job_id,numeric_run:job.id,spatial_task:source.task_id,numeric_task:task.id,measurements,pixel,numeric_scores:numeric.data.scores,output_count:descriptor.outputs.length,download_hash:source.outputs[0].sha256,scope:'Actual full-grid spatial outputs and independent numeric fixture; business validation remains false; numerical setup via API is not counted as user-minimal-fill evidence.'},null,2));
});
