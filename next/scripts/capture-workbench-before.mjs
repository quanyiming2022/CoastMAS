import { chromium } from '../web/node_modules/playwright-core/index.mjs';
import fs from 'node:fs/promises';
const access=JSON.parse(await fs.readFile(new URL('../.state/clean-verify-20260924b/settings-access.json',import.meta.url),'utf8'));
const output=new URL('../artifacts/professional-workbench-before/',import.meta.url);await fs.mkdir(output,{recursive:true});
const browser=await chromium.launch({channel:'chromium',headless:true});
try {
 const page=await browser.newPage();await page.goto('http://127.0.0.1:58012/library?project='+access.project_id);
 await page.getByLabel('邮箱',{exact:true}).fill(access.email);await page.getByLabel('密码',{exact:true}).fill(access.password);
 await page.getByRole('button',{name:'登录',exact:true}).click();await page.getByRole('heading',{name:'数据资源',exact:true}).waitFor();
 await page.getByLabel('查找资料',{exact:true}).fill('PRD_distance_water');
 await page.getByRole('button',{name:'PRD_distance_water.tif',exact:true}).first().click();
 await page.getByText('实际数据层已显示',{exact:true}).waitFor({timeout:60000});
 for(const [width,height] of [[1440,900],[1366,768],[390,844]]) {
  await page.setViewportSize({width,height});await page.screenshot({path:new URL(`catalog-${width}.png`,output).pathname});
 }
 await fs.writeFile(new URL('capture.json',output),JSON.stringify({url:page.url(),captured_at:new Date().toISOString(),scope:'prior running build, same existing real water raster'},null,2));
 console.log('Three before screenshots captured from running isolated service');
} finally {await browser.close();}
