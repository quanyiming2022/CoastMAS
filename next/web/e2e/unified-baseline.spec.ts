import { test, expect } from '@playwright/test';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { evidenceDirectory, evidencePath } from './evidence';

test('N01 read-only deployed build baseline', async ({page}) => {
  const access=JSON.parse(await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE!, 'utf8'));
  const writes:string[]=[];
  await page.route('**/api/**', async route => {
    const req=route.request();
    if (!['GET','HEAD'].includes(req.method()) && !req.url().endsWith('/api/session')) {
      writes.push(req.method()+' '+new URL(req.url()).pathname);
      await route.abort('blockedbyclient');
    } else await route.continue();
  });
  await mkdir(evidenceDirectory,{recursive:true});
  await page.setViewportSize({width:1440,height:900});
  await page.goto('/research?project='+access.project_id);
  await page.getByLabel('邮箱',{exact:true}).fill(access.email);
  await page.getByLabel('密码',{exact:true}).fill(access.password);
  await page.getByRole('button',{name:'登录',exact:true}).click();
  await expect(page.getByRole('link',{name:'数据源与系统设置',exact:true})).toBeVisible();
  const evidence:{page:string;text:string}[]=[];
  for (const label of ['数据源与系统设置','项目管理','用户管理','数据资源','方法方案']) {
    await page.getByRole('link',{name:label,exact:true}).click();
    await expect(page.getByRole('link',{name:label,exact:true})).toHaveAttribute('aria-current','page');
    await page.screenshot({path:evidencePath('before-'+label+'-1440.png')});
    evidence.push({page:label,text:await page.locator('main').innerText()});
  }
  await writeFile(evidencePath('deployed-readonly.json'),JSON.stringify({url:page.url(),evidence,blocked_writes:writes,scientific_mutations:0},null,2));
});
