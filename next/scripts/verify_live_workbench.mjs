import {chromium} from '../web/node_modules/playwright-core/index.mjs';
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
const access=JSON.parse(await fs.readFile(new URL('../.state/settings-access.json',import.meta.url),'utf8'));
const output=new URL('../artifacts/professional-live/',import.meta.url);await fs.mkdir(output,{recursive:true});
const browser=await chromium.launch({channel:'chromium',headless:true});
try {
 const page=await browser.newPage({viewport:{width:1440,height:900}});const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.goto('http://127.0.0.1:58010/library?project='+access.project_id);
 await page.getByLabel('邮箱',{exact:true}).fill(access.email);await page.getByLabel('密码',{exact:true}).fill(access.password);await page.getByRole('button',{name:'登录',exact:true}).click();
 await page.getByRole('heading',{name:'研究工作台',exact:true}).waitFor();
 await page.getByLabel('查找资料',{exact:true}).fill('PRD_distance_construction');await page.getByLabel('查找资料',{exact:true}).press('Enter');
 await page.getByRole('button',{name:'PRD_distance_construction land.tif',exact:true}).first().click();
 await page.getByText('实际数据层已显示',{exact:true}).waitFor({timeout:60000});
 await page.screenshot({path:new URL('workbench-1440.png',output).pathname});
 const scripts=await page.locator('script[src]').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('src')));
 const served=[];
 for(const source of scripts){const response=await page.request.get(new URL(source,page.url()).href);served.push({url:source,status:response.status(),sha256:createHash('sha256').update(await response.body()).digest('hex')});}
 const health=await(await page.request.get('http://127.0.0.1:58010/health')).json();
 if(errors.length)throw new Error('Live page errors: '+errors.join(';'));
 await fs.writeFile(new URL('verification.json',output),JSON.stringify({url:page.url(),health,served,page_errors:errors,scope:'Existing authorized real asset viewed; no analysis, rename, recycle or source data mutation',verified_at:new Date().toISOString()},null,2));
 console.log('58010 actual browser, actual source layer and served build verified');
} finally {await browser.close();}
