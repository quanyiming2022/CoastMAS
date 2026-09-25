import { test, expect } from '@playwright/test';
import { readFile,mkdir,writeFile } from 'node:fs/promises';
import { evidenceDirectory,evidencePath } from './evidence';

test('U61 AHP matrix and optimization rules publish real fixed method versions',async({page})=>{
  test.setTimeout(120000);if(!process.env.COASTMAS_NEXT_TEST_URL?.endsWith(':58013'))throw new Error('Isolated only');
  const access=JSON.parse(await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE!,'utf8'));await mkdir(evidenceDirectory,{recursive:true});
  await page.setViewportSize({width:1440,height:900});await page.goto('/methods');await page.getByLabel('邮箱',{exact:true}).fill(access.email);await page.getByLabel('密码',{exact:true}).fill(access.password);await page.getByRole('button',{name:'登录',exact:true}).click();await expect(page.getByRole('button',{name:'新建研究',exact:true})).toBeVisible();
  const session=await (await page.request.get('/api/session')).json(),headers={'X-CSRF-Token':session.csrf};
  const project=await (await page.request.post('/api/projects',{headers,data:{name:'权重和优化验收-'+Date.now()}})).json();
  await page.goto('/methods?project='+project.id);const catalog=page.getByRole('region',{name:'方法方案',exact:true});
  await catalog.getByRole('button',{name:'新建',exact:true}).click();const editor=page.getByRole('region',{name:'方法方案编辑',exact:true});
  await editor.getByLabel('方法名称',{exact:true}).fill('明确AHP工程基准');if(!await editor.getByLabel('方法科学依据').isVisible())await editor.getByText('方案说明与依据',{exact:true}).click();await editor.getByLabel('方法科学依据').fill('数学比值基准：a:b:c=2:3:5；只用于数值验收。');
  for(let i=1;i<=3;i++){await editor.getByRole('button',{name:'添加指标',exact:true}).click();await editor.getByLabel(`第${i}项指标`,{exact:true}).fill(['a','b','c'][i-1]!);await editor.getByLabel(`第${i}项单位`,{exact:true}).fill('1');await editor.getByLabel(`第${i}项下限`,{exact:true}).fill('0');await editor.getByLabel(`第${i}项上限`,{exact:true}).fill('1');await editor.getByLabel(`第${i}项方向`,{exact:true}).selectOption('positive');}
  await editor.getByRole('combobox',{name:'综合方式',exact:true}).selectOption('ahp');await editor.getByText('导入已有CSV/XLSX矩阵',{exact:true}).click();
  const matrix='指标,c,a,b\nc,1,5/2,5/3\na,2/5,1,2/3\nb,3/5,3/2,1\n';
  await editor.getByLabel('判断矩阵文件').setInputFiles({name:'ratios.csv',mimeType:'text/csv',buffer:Buffer.from(matrix)});await editor.getByRole('button',{name:'读取并匹配判断矩阵',exact:true}).click();
  await expect(editor.locator('.ahp-weights')).toContainText('0.200000');await expect(editor.locator('.ahp-weights')).toContainText('0.300000');await expect(editor.locator('.ahp-weights')).toContainText('0.500000');
  await editor.getByRole('button',{name:'发布固定版本',exact:true}).click();await expect(editor.getByRole('status').first()).toHaveText('已发布，待批准');await editor.getByRole('button',{name:'批准第1版',exact:true}).click();await expect(editor.getByRole('status').first()).toHaveText('已批准第1版');
  await page.screenshot({path:evidencePath('ahp-matrix-1440.png')});await editor.getByRole('button',{name:'返回方法目录',exact:true}).click();
  await catalog.getByRole('button',{name:'新建',exact:true}).click();await editor.getByRole('combobox',{name:'综合方式',exact:true}).selectOption('binary_allocation');
  await editor.getByLabel('方法名称',{exact:true}).fill('明确约束的优化工程基准');if(!await editor.getByLabel('方法科学依据').isVisible())await editor.getByText('方案说明与依据',{exact:true}).click();await editor.getByLabel('方法科学依据').fill('独立二元预算测试，不代表实际土地分配建议。');
  for(const label of ['效益','成本','面积','生态代价','风险']){await editor.getByLabel(label+'指标',{exact:true}).fill(label);await editor.getByLabel(label+'单位',{exact:true}).fill(label==='面积'?'m^2':'1');}
  await editor.getByLabel('保护标记含义').fill('保护');await editor.getByLabel('风险可加性依据').fill('工程夹具各单元风险定义为独立可加指数。');
  for(const [label,value] of [['总预算','10'],['最小面积','1'],['生态代价上限','10'],['风险上限','10']])await editor.getByLabel(label,{exact:true}).fill(value);
  await editor.getByRole('button',{name:'发布固定版本',exact:true}).click();await expect(editor.getByRole('status').first()).toHaveText('已发布，待批准');await editor.getByRole('button',{name:'批准第1版',exact:true}).click();await expect(editor.getByRole('status').first()).toHaveText('已批准第1版');
  await page.screenshot({path:evidencePath('optimization-method-1440.png')});await editor.getByRole('button',{name:'返回方法目录',exact:true}).click();
  const templates=await (await page.request.get(`/api/projects/${project.id}/templates`)).json();expect(templates).toHaveLength(2);
  const ahp=templates.find((m:{spec:{configuration:{weighting?:unknown}}})=>m.spec.configuration.weighting);expect(ahp.spec.configuration.indicators.map((i:{weight:number})=>i.weight)).toEqual(expect.arrayContaining([expect.closeTo(.2,12),expect.closeTo(.3,12),expect.closeTo(.5,12)]));
  const taskCount=(await (await page.request.get(`/api/management/catalog/tasks?project=${project.id}`)).json()).total;expect(taskCount).toBe(0);
  await writeFile(evidencePath('weighting-flow.json'),JSON.stringify({project:project.id,ahpId:ahp.id,weights:ahp.spec.configuration.indicators.map((i:{weight:number})=>i.weight),matrixSource:ahp.spec.configuration.weighting.source,taskCount,optimization:templates.find((m:{spec:{configuration:{task:string}}})=>m.spec.configuration.task==='optimization').id},null,2));
});
