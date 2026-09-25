import {test,expect} from '@playwright/test';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {evidencePath,evidenceDirectory} from './evidence';
test('independent eight panels preserve task and never execute by opening',async({page})=>{
 test.setTimeout(90000);if(!process.env.COASTMAS_NEXT_TEST_URL?.endsWith(':58013'))throw new Error('Isolated only');
 const fixture=JSON.parse(await readFile(process.env.COASTMAS_NEXT_STEP_BASELINE!,'utf8')),a=JSON.parse(await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE!,'utf8'));
 await mkdir(evidenceDirectory,{recursive:true});await page.setViewportSize({width:1440,height:900});await page.goto('/tasks/'+fixture.task.id+'?project='+fixture.project);await page.getByLabel('邮箱',{exact:true}).fill(a.email);await page.getByLabel('密码',{exact:true}).fill(a.password);await page.getByRole('button',{name:'登录',exact:true}).click();await expect(page.getByRole('navigation',{name:'研究环节'})).toBeVisible();
 const entries=[];for(const [index,title] of ['资料装配','空间统一','统计空间化','指标生产','指标标准化','权重配置','综合计算','验证与交付'].entries()){
 const requests:string[]=[];const observe=(r:{url:()=>string;method:()=>string})=>{if(r.url().includes('/api/'))requests.push(r.method()+' '+new URL(r.url()).pathname)};page.on('request',observe);
 await page.getByRole('navigation',{name:'研究环节'}).getByRole('button',{name:new RegExp(title)}).click();const panel=page.getByRole('complementary',{name:'研究共用右侧面板'});await expect(panel).toBeVisible();await page.mouse.move(700,30);await expect(panel.getByLabel('任务名称',{exact:true})).toHaveCount(0);await expect(panel.getByRole('button',{name:'检查草稿缺口',exact:true})).toHaveCount(0);await expect(panel.getByRole('button',{name:'最大化配置表',exact:true})).toHaveCount(0);await expect(panel.locator('.task-workspace')).toHaveCount(0);await page.screenshot({path:evidencePath(`step-${index+1}-after.png`)});entries.push({step:title,text:await panel.innerText(),requests});page.off('request',observe);expect(requests.filter(r=>r.includes('/execute')||r.includes('/preflight')||r.includes('/processing-nodes'))).toEqual([]);
 }
 await writeFile(evidencePath('eight-panels-after.json'),JSON.stringify({project:fixture.project,task:fixture.task.id,build:'unified-business-dev9',entries,scope:'Structural browser regression; missing scientific services remain unaccepted'},null,2));
});
