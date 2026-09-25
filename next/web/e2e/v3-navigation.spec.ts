import {test,expect} from '@playwright/test';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {randomUUID} from 'node:crypto';
import {evidenceDirectory,evidencePath} from './evidence';

test('V3 actual shell routes, four task flows, permissions and research preservation',async({page,browser})=>{
  test.setTimeout(120000);
  if(!process.env.COASTMAS_NEXT_TEST_URL?.endsWith(':58013'))throw new Error('isolated environment only');
  const access=JSON.parse(await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE!,'utf8'));
  const baseline=JSON.parse(await readFile(evidencePath('nav-baseline.json'),'utf8'));
  await mkdir(evidenceDirectory,{recursive:true});
  await page.goto('/');await page.getByLabel('邮箱',{exact:true}).fill(access.email);await page.getByLabel('密码',{exact:true}).fill(access.password);await page.getByRole('button',{name:'登录',exact:true}).click();await expect(page.getByRole('link',{name:'工作台',exact:true})).toBeVisible();
  await page.goto(`/tasks/${baseline.task}?project=${baseline.project}`);
  const nav=page.locator('.workspace-rail').getByRole('navigation',{name:'主要功能'});
  for(const group of ['项目与研究','数据','指标与方法','模型工程','耦合与工作流','规划与优化','运行','成果','管理'])await expect(nav.getByRole('button',{name:group,exact:true})).toBeVisible();
  for(const old of ['研究业务','资料与方法','运行与成果','管理中心'])await expect(nav.getByText(old,{exact:true})).toHaveCount(0);
  const before=await(await page.request.get('/api/tasks/'+baseline.task)).json();
  async function open(group:string,label:string) {
    const button=nav.getByRole('button',{name:group,exact:true});if(await button.getAttribute('aria-expanded')!=='true')await button.click();await nav.getByRole('link',{name:label,exact:true}).click();
  }
  for(const [group,label,region] of [['模型工程','模型目录','模型目录'],['耦合与工作流','数据—模型匹配','数据—模型匹配'],['规划与优化','规划任务','规划任务'],['指标与方法','指标库','指标库']]){
    await open(group!,label!);await expect(page.getByRole('region',{name:region!,exact:true})).toBeVisible();
  }
  await open('项目与研究','项目');await expect(page).toHaveURL(/\/projects\?/);await expect(page.getByRole('heading',{name:'项目管理',exact:true,level:1})).toBeVisible();
  await nav.getByRole('link',{name:'工作台',exact:true}).click();
  const after=await(await page.request.get('/api/tasks/'+baseline.task)).json();expect(after).toEqual(before);
  await expect(page.getByRole('button',{name:/^指标 ·/})).toBeVisible();
  for(const [width,height] of [[1440,900],[1366,768],[1920,1080],[2560,1440]]){
    await page.setViewportSize({width:width!,height:height!});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:evidencePath(`nav-after-${width}.png`)});
  }
  const types:Record<string,string[]>={assessment:['数据','准备与对齐','指标','权重与评价','综合计算','分级','时空分析','成果'],simulation:['数据','准备与对齐','状态变量','模型','情景条件','模拟运行','情景分析','成果'],planning:['数据','准备与对齐','现状诊断','规划目标','约束与决策变量','方案生成与优化','方案评价与比较','规划成果'],comparison:['选择方案','统一比较口径','评价指标','统计分析','空间差异','权衡分析','敏感性分析','比较成果']};
  const created=[];
  for(const [type,steps] of Object.entries(types)){
    await open('项目与研究','研究任务');await page.getByRole('button',{name:'新建研究',exact:true}).click();const dialog=page.getByRole('dialog',{name:'新建研究任务'});await dialog.getByRole('combobox',{name:'任务类型',exact:true}).selectOption(type);
    const reply=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/tasks'&&r.request().method()==='POST');await dialog.getByRole('button',{name:'创建并继续'}).click();const response=await reply;expect(response.status()).toBe(201);const task=await response.json();created.push({type,id:task.id});expect(task.draft.options.task_type).toBe(type);
    const rail=page.getByRole('navigation',{name:'研究环节'});await expect(rail.getByRole('button')).toHaveCount(8);for(const step of steps)await expect(rail.getByRole('button',{name:new RegExp('^'+step+' ·')})).toBeVisible();
    const current=await(await page.request.get(`/api/tasks/${task.id}/jobs`)).json();expect(current.total).toBe(0);
  }
  const session=await(await page.request.get('/api/session')).json(),headers={'X-CSRF-Token':session.csrf};
  const email=`nav-viewer-${randomUUID()}@example.test`,password=randomUUID()+randomUUID();
  const accountResponse=await page.request.post('/api/accounts',{headers,data:{email,password,system_admin:false}});expect(accountResponse.status()).toBe(201);const account=await accountResponse.json();
  expect((await page.request.put(`/api/projects/${baseline.project}/members/${account.id}`,{headers,data:{role:'viewer'}})).status()).toBe(200);
  const context=await browser.newContext();const viewer=await context.newPage();await viewer.goto(process.env.COASTMAS_NEXT_TEST_URL!);await viewer.getByLabel('邮箱',{exact:true}).fill(email);await viewer.getByLabel('密码',{exact:true}).fill(password);await viewer.getByRole('button',{name:'登录',exact:true}).click();await expect(viewer.getByRole('link',{name:'工作台',exact:true})).toBeVisible();
  await expect(viewer.getByRole('link',{name:'用户与权限',exact:true})).toHaveCount(0);expect((await viewer.request.get(process.env.COASTMAS_NEXT_TEST_URL!+'/api/accounts')).status()).toBe(403);
  await viewer.goto(process.env.COASTMAS_NEXT_TEST_URL!+`/models?project=${baseline.project}`);await expect(viewer.getByRole('region',{name:'模型目录',exact:true})).toBeVisible();await expect(viewer.getByRole('button',{name:'批准此固定版本'})).toHaveCount(0);await context.close();
  await writeFile(evidencePath('navigation-flow.json'),JSON.stringify({baseline,created,task_unchanged:true,admin_and_viewer:true,source:'actual UI/API',build:'master-v3-dev19',limitations:['dynamic simulation and unconnected domain steps are unavailable; no calculation pass inferred']},null,2));
});
