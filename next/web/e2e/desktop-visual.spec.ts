import {test,expect} from '@playwright/test';
import {readFile,writeFile} from 'node:fs/promises';
import {evidencePath} from './evidence';
test('desktop domains share visual primitives and Dock retains the fixed result',async({page})=>{
  test.setTimeout(120000);
  if(!process.env.COASTMAS_NEXT_TEST_URL?.endsWith(':58013'))throw new Error('isolated environment only');
  const access=JSON.parse(await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE!,'utf8'));
  const flow=JSON.parse(await readFile(evidencePath('indicator-flow.json'),'utf8'));
  await page.goto('/');await page.getByLabel('邮箱',{exact:true}).fill(access.email);await page.getByLabel('密码',{exact:true}).fill(access.password);await page.getByRole('button',{name:'登录',exact:true}).click();await expect(page.getByRole('link',{name:'工作台',exact:true})).toBeVisible();
  await page.goto(`/tasks/${flow.task}?project=${flow.project}`);
  await expect(page.locator('.research-result .maplibregl-canvas')).toBeVisible();
  const initial=await(await page.request.get(`/projects/${flow.project}/workspace-state`.replace('/projects','/api/projects'))).json();
  const metrics:unknown[]=[];
  const mapElement=await page.locator('.research-result .maplibregl-canvas').elementHandle();
  const nav=page.locator('.workspace-rail').getByRole('navigation',{name:'主要功能'});
  async function capture(name:string) {
    await expect(page.locator('.research-result').getByRole('status',{name:'图层就绪',exact:true})).toBeVisible();
    for(const [width,height] of [[1440,900],[1366,768],[1920,1080],[2560,1440]]) {
      await page.setViewportSize({width:width!,height:height!});await page.mouse.move(10,10);await expect(page.locator('.research-result').getByRole('status',{name:'图层就绪',exact:true})).toBeVisible();
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      const data=await page.evaluate(()=>({bodyFont:getComputedStyle(document.documentElement).fontSize,topbar:document.querySelector('.workspace-topbar')!.getBoundingClientRect().height,canvas:[...document.querySelectorAll('.research-result .maplibregl-canvas')].map(el=>{const r=el.getBoundingClientRect();return {top:r.top,height:r.height,width:r.width};})}));
      expect(data.bodyFont).toBe('13px');expect(data.topbar).toBeLessThanOrEqual(48);metrics.push({name,width,height,...data});
      await page.screenshot({path:evidencePath(`desktop-${name}-${width}.png`)});
    }
  }
  for(const [group,label,region,name] of [['数据','数据资源','', 'data'],['指标与方法','综合评价方法','','methods'],['规划与优化','规划任务','规划任务','planning'],['运行','运行记录','','runs'],['成果','数据成果','','results']]) {
    const toggle=nav.getByRole('button',{name:group!,exact:true});if(await toggle.getAttribute('aria-expanded')!=='true')await toggle.click();await nav.getByRole('link',{name:label!,exact:true}).click();
    expect(await mapElement!.evaluate(el=>el.isConnected)).toBe(true);
    if(region)await expect(page.getByRole('region',{name:region,exact:true})).toBeVisible();
    await expect(page.getByRole('separator',{name:'调整目录高度'})).toBeVisible();
    await capture(name!);
  }
  const splitter=page.getByRole('separator',{name:'调整目录高度'});const box=(await splitter.boundingBox())!;const before=Number(await splitter.getAttribute('aria-valuenow'));
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2,box.y-60,{steps:6});await page.mouse.up();expect(Number(await splitter.getAttribute('aria-valuenow'))).toBeGreaterThan(before);
  await page.getByRole('button',{name:'最大化表格',exact:true}).click();await expect(page.getByRole('button',{name:'恢复面板',exact:true})).toBeVisible();await page.getByRole('button',{name:'恢复面板',exact:true}).click();await page.getByRole('button',{name:'关闭目录',exact:true}).click();
  await expect(page.locator('.research-result .maplibregl-canvas')).toBeVisible();
  const restored=await(await page.request.get(`/api/projects/${flow.project}/workspace-state`)).json();expect(restored.state.active_task_id).toBe(initial.state.active_task_id);expect(restored.state.viewed_job_id).toBe(flow.job);
  await capture('result-map');
  await writeFile(evidencePath('desktop-measurements.json'),JSON.stringify({metrics,dock_resize:true,restore:true,run:flow.job,coverage_limitations:['AHP editor, complete Planning/Comparison business paths and before screenshots for all domain pages remain unverified']},null,2));
});
