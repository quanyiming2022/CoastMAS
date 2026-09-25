import {createRequire} from 'node:module';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {dirname,resolve,join} from 'node:path';
const ROOT=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const require=createRequire(join(ROOT,'next/web/package.json'));
const {chromium,expect}=require('@playwright/test');
const base='http://127.0.0.1:58125';
const folder=join(ROOT,'.review/evidence/runs/v3-audit-20260925');
const images=join(ROOT,'.review/evidence/screenshots/v3-audit-20260925');
const access=JSON.parse(await readFile(join(ROOT,'next/.state/v3-audit-20260925/settings-access.json'),'utf8'));
const fixture=join(ROOT,'next/.state/v3-audit-20260925/fixtures');
await mkdir(images,{recursive:true});
const browser=await chromium.launch({channel:'chromium'});
const context=await browser.newContext({baseURL:base,viewport:{width:1440,height:900}});
const page=await context.newPage();
const result={base,fixture_kind:'engineering_fixture',actions:[],steps:[],navigation:[],requests:[],screenshots:[],page_errors:[],tasks:{},scope:'actual browser; no product source changes'};
page.on('pageerror',e=>result.page_errors.push(e.message));
page.on('response',async response=>{
 const u=new URL(response.url());if(!u.pathname.startsWith('/api/')||u.pathname==='/api/session')return;
 const row={method:response.request().method(),path:u.pathname,status:response.status()};
 if(response.status()>=400){try{const body=await response.json();row.code=body.code??null;row.message=body.message??null;row.validation=Array.isArray(body.detail)?body.detail.map(x=>({type:x.type,loc:x.loc,msg:x.msg})):body.detail;}catch{}}
 result.requests.push(row);
});
async function action(name,fn){try{const detail=await fn();result.actions.push({name,status:'WORKING',detail});console.log('WORKING',name);return detail;}catch(e){result.actions.push({name,status:'BROKEN',error:String(e.message).slice(0,1200)});console.log('BROKEN',name);return null;}finally{await writeFile(join(folder,'browser.json'),JSON.stringify(result,null,2));}}
async function capture(name){await page.screenshot({path:join(images,name+'.png')});result.screenshots.push(name+'.png');}
async function bodySummary(){return page.evaluate(()=>({headings:[...document.querySelectorAll('h1,h2,h3')].map(x=>x.textContent),buttons:[...document.querySelectorAll('button')].filter(x=>x.getClientRects().length).map(x=>({text:x.innerText,label:x.getAttribute('aria-label'),disabled:x.disabled})),fields:[...document.querySelectorAll('input,select,textarea')].filter(x=>x.getClientRects().length).map(x=>({type:x.type,label:x.getAttribute('aria-label')||x.closest('label')?.innerText||null})),alerts:[...document.querySelectorAll('[role=alert]')].map(x=>x.textContent),overflow:document.documentElement.scrollWidth>innerWidth}));}
try{
 await action('login',async()=>{await page.goto('/research');await page.getByLabel('邮箱',{exact:true}).fill(access.email);await page.getByLabel('密码',{exact:true}).fill(access.password);await page.getByRole('button',{name:'登录',exact:true}).click();await expect(page.getByRole('link',{name:'工作台',exact:true})).toBeVisible();return {account:'isolated audit administrator'};});
 for(const type of ['assessment','simulation','planning','comparison']){
  await action('create-'+type,async()=>{await page.getByRole('button',{name:'新建研究',exact:true}).click();const modal=page.getByRole('dialog',{name:'新建研究任务'});await modal.getByLabel('任务类型').selectOption(type);await modal.getByLabel('任务名称（可选）').fill('V3审计-'+type);await modal.getByRole('button',{name:'创建并继续',exact:true}).click();await expect(modal).not.toBeVisible();await expect(page.locator('.research-flow-rail button')).toHaveCount(8);const id=new URL(page.url()).pathname.split('/').pop();result.tasks[type]=id;return await (await page.request.get('/api/tasks/'+id)).json();});
  if(!result.tasks[type])continue;
  const id=result.tasks[type];const before=await (await page.request.get('/api/tasks/'+id)).json();
  for(let i=0;i<8;i++)await action('step-'+type+'-'+(i+1),async()=>{const button=page.locator('.research-flow-rail button').nth(i);const label=await button.getAttribute('aria-label');await button.click();const panel=page.getByRole('complementary',{name:'研究共用右侧面板'});await expect(panel).toBeVisible();const row={type,index:i+1,label,text:(await panel.innerText()).slice(0,8000),ui:await bodySummary()};result.steps.push(row);if(i===3||type==='simulation'&&i===5)await capture(type+'-step-'+(i+1));return {label,text:row.text};});
  await action('restore-'+type,async()=>{await page.reload();await expect(page.locator('.research-flow-rail button')).toHaveCount(8);const after=await (await page.request.get('/api/tasks/'+id)).json();expect(after.draft).toEqual(before.draft);const jobs=await(await page.request.get('/api/tasks/'+id+'/jobs')).json();return {same_draft:true,jobs};});
 }
 await page.goto('/research?project='+access.project_id);
 const nav=page.getByRole('navigation',{name:'主要功能'});
 for(const group of ['项目与研究','数据','指标与方法','模型工程','耦合与工作流','规划与优化','运行','成果','管理']){const b=nav.getByRole('button',{name:group,exact:true});if(await b.getAttribute('aria-expanded')!=='true')await b.click();}
 result.navigation=await nav.evaluate(el=>[...el.querySelectorAll('a,button')].map(e=>({name:e.textContent?.trim(),href:e.getAttribute('href'),disabled:e.disabled??false,aria_disabled:e.getAttribute('aria-disabled')})));
 const links=result.navigation.filter(x=>x.href).map(x=>({name:x.name,href:x.href}));
 for(const link of links)await action('navigate-'+link.name,async()=>{await page.goto(link.href);await expect(page.getByRole('link',{name:'工作台',exact:true})).toBeVisible();await expect(page.locator('.login')).toHaveCount(0);return {href:link.href,...await bodySummary()};});
 const task=result.tasks.assessment;
 await page.goto('/tasks/'+task);
 await action('import-geotiff-and-bind',async()=>{await page.getByRole('button',{name:/^数据 ·/}).click();await page.getByRole('complementary',{name:'研究共用右侧面板'}).getByRole('button',{name:'添加资料',exact:true}).click();const dialog=page.getByRole('dialog',{name:'添加研究输入'});await dialog.getByRole('button',{name:'导入新资料',exact:true}).click();await dialog.getByLabel('选择并导入资料',{exact:true}).setInputFiles(join(fixture,'red-nir.tif'));await expect(page.getByRole('tab',{name:'输入 1',exact:true})).toBeVisible();await capture('import-feedback');const summary=await bodySummary();await dialog.getByRole('button',{name:'关闭',exact:true}).click();return {ui:summary,task:await(await page.request.get('/api/tasks/'+task)).json()};});
 await action('indicator-picker',async()=>{await page.getByRole('button',{name:/^指标 ·/}).click();const picker=page.getByRole('region',{name:'指标选择器',exact:true});await expect(picker).toBeVisible();await capture('indicator-picker');return {text:(await picker.innerText()).slice(0,15000),ui:await bodySummary()};});
 await action('weight-user-flow',async()=>{await page.getByRole('button',{name:/^权重与评价 ·/}).click();await capture('weight-method-gate');return await bodySummary();});
 await action('method-builtins-dialog',async()=>{await page.goto('/methods?project='+access.project_id);const b=page.getByRole('button',{name:'新建方法',exact:true});await expect(b).toBeVisible();await b.click();const summary=await bodySummary();await capture('method-create');return summary;});
 await page.goto('/tasks/'+task);
 for(const [width,height] of [[1440,900],[1366,768],[1920,1080],[2560,1440]])await action('viewport-'+width,async()=>{await page.setViewportSize({width,height});const close=page.getByRole('button',{name:'关闭右侧面板',exact:true});if(await close.isVisible())await close.click();await capture('workspace-'+width);return await page.evaluate(()=>{const map=document.querySelector('.maplibregl-map');const b=map?.getBoundingClientRect();return {width:innerWidth,height:innerHeight,overflow:document.documentElement.scrollWidth>innerWidth,map:b?{x:b.x,y:b.y,width:b.width,height:b.height}:null,font:getComputedStyle(document.body).fontSize,rail:document.querySelector('.research-flow-rail')?.getBoundingClientRect().width};});});
}finally{await writeFile(join(folder,'browser.json'),JSON.stringify(result,null,2));await browser.close();}
