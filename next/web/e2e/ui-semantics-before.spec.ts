import {test,expect} from '@playwright/test';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {evidencePath,evidenceDirectory} from './evidence';
test('capture existing dev8 empty and populated step behavior (baseline only)',async({page})=>{
 test.setTimeout(90000);if(!process.env.COASTMAS_NEXT_TEST_URL?.endsWith(':58013'))throw new Error('Isolated only');
 const a=JSON.parse(await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE!,'utf8'));await mkdir(evidenceDirectory,{recursive:true});
 await page.goto('/research');await page.getByLabel('邮箱',{exact:true}).fill(a.email);await page.getByLabel('密码',{exact:true}).fill(a.password);await page.getByRole('button',{name:'登录',exact:true}).click();await expect(page.getByRole('button',{name:'新建研究',exact:true})).toBeVisible();
 const session=await(await page.request.get('/api/session')).json(),headers={'X-CSRF-Token':session.csrf};
 const p=await(await page.request.post('/api/projects',{headers,data:{name:'界面语义验收 '+Date.now()}})).json();
 const t=await(await page.request.post('/api/tasks',{headers,data:{project_id:p.id,goal:'comprehensive-assessment',title:'空输入研究'}})).json();
 await page.goto('/tasks/'+t.id+'?project='+p.id);await page.getByRole('navigation',{name:'研究环节'}).getByRole('button',{name:/资料装配/}).click();
 const panel=page.getByRole('complementary',{name:'研究共用右侧面板'});await expect(panel.getByRole('button',{name:'检查草稿缺口',exact:true})).toBeVisible();
 const calls:string[]=[];page.on('request',r=>{if(r.url().includes('/api/'))calls.push(r.method()+' '+new URL(r.url()).pathname)});
 for(const [width,height] of [[1440,900],[1366,768]]){await page.setViewportSize({width:width!,height:height!});await page.screenshot({path:evidencePath(`empty-before-${width}.png`)});}
 await panel.getByRole('button',{name:'检查草稿缺口',exact:true}).click();await expect(panel.getByText('请选择当前任务要使用的资料：selection',{exact:true})).toBeVisible();
 const before=await(await page.request.get('/api/tasks/'+t.id)).json();await panel.getByRole('button',{name:'最大化配置表',exact:true}).click();await expect(page.locator('[data-configuration]')).toHaveAttribute('data-configuration','true');
 expect(await(await page.request.get('/api/tasks/'+t.id)).json()).toEqual(before);
 await writeFile(evidencePath('baseline.json'),JSON.stringify({project:p.id,task:t.id,calls,task:before,scope:'Capture only; not acceptance PASS.'},null,2));
});
