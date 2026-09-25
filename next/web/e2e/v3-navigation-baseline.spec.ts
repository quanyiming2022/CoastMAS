import {test,expect} from '@playwright/test';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {evidenceDirectory,evidencePath} from './evidence';
test('capture actual pre-correction build in an isolated navigation project',async({page})=>{
  if(!process.env.COASTMAS_NEXT_TEST_URL?.endsWith(':58013'))throw new Error('isolated environment only');
  const access=JSON.parse(await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE!,'utf8'));
  await mkdir(evidenceDirectory,{recursive:true});await page.goto('/');await page.getByLabel('邮箱',{exact:true}).fill(access.email);await page.getByLabel('密码',{exact:true}).fill(access.password);await page.getByRole('button',{name:'登录',exact:true}).click();await expect(page.getByRole('link',{name:'工作台',exact:true})).toBeVisible();
  const session=await(await page.request.get('/api/session')).json(),headers={'X-CSRF-Token':session.csrf};
  const project=await(await page.request.post('/api/projects',{headers,data:{name:'V3导航隔离验收 '+Date.now()}})).json();
  const task=await(await page.request.post('/api/tasks',{headers,data:{project_id:project.id,title:'V3导航现场恢复验收',goal:'comprehensive-assessment'}})).json();
  await page.goto(`/tasks/${task.id}?project=${project.id}`);await expect(page.getByRole('button',{name:/指标生产/})).toBeVisible();
  for(const [width,height] of [[1440,900],[1366,768],[1920,1080],[2560,1440]]){await page.setViewportSize({width:width!,height:height!});await page.screenshot({path:evidencePath(`nav-before-${width}.png`)});}
  await writeFile(evidencePath('nav-baseline.json'),JSON.stringify({project:project.id,task:task.id,revision:task.revision}));
});
