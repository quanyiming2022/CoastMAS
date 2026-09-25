import {test,expect} from '@playwright/test';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {evidencePath,evidenceDirectory} from './evidence';
test('capture all eight dev8 panels and actual requests before structural replacement',async({page})=>{
 test.setTimeout(90000);if(!process.env.COASTMAS_NEXT_TEST_URL?.endsWith(':58013'))throw new Error('Isolated only');
 const fixture=JSON.parse(await readFile(process.env.COASTMAS_NEXT_STEP_BASELINE!,'utf8')),a=JSON.parse(await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE!,'utf8'));
 await mkdir(evidenceDirectory,{recursive:true});await page.setViewportSize({width:1440,height:900});await page.goto('/tasks/'+fixture.task.id+'?project='+fixture.project);await page.getByLabel('邮箱',{exact:true}).fill(a.email);await page.getByLabel('密码',{exact:true}).fill(a.password);await page.getByRole('button',{name:'登录',exact:true}).click();await expect(page.getByRole('navigation',{name:'研究环节'})).toBeVisible();
 const entries=[];for(const [index,title] of ['资料装配','空间统一','统计空间化','指标生产','指标标准化','权重配置','综合计算','验证与交付'].entries()){
 const requests:string[]=[];const observe=(r:{url:()=>string;method:()=>string})=>{if(r.url().includes('/api/'))requests.push(r.method()+' '+new URL(r.url()).pathname)};page.on('request',observe);
 await page.getByRole('navigation',{name:'研究环节'}).getByRole('button',{name:new RegExp(title)}).click();const panel=page.getByRole('complementary',{name:'研究共用右侧面板'});await expect(panel).toBeVisible();await page.screenshot({path:evidencePath(`step-${index+1}-before.png`)});entries.push({step:title,text:await panel.innerText(),requests});page.off('request',observe);
 }
 await writeFile(evidencePath('eight-panels-before.json'),JSON.stringify({project:fixture.project,task:fixture.task.id,build:'unified-business-dev8',entries,scope:'Baseline capture only; no acceptance PASS'},null,2));
});
