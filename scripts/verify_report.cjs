/* Browser integration check against reports produced by the Python CLI.
   Development only: playwright on NODE_PATH; TOKENME_BROWSER may name local Chrome. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawnSync}=require('node:child_process');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),out=path.resolve(root,process.argv[2]||'.local/report-smoke');
fs.mkdirSync(out,{recursive:true});
function cli(args){
 const result=spawnSync(process.env.TOKENME_PYTHON||'python',['-m','token_footprint',...args,'--json'],{cwd:root,encoding:'utf8'});
 assert.equal(result.status,0,result.stderr);return JSON.parse(result.stdout).data;
}
function makeReport(tier){
 const total=[3800000,38000000,380000000,3800000000,38000000000][tier-1],folder=path.join(out,`L${tier}`);
 fs.mkdirSync(folder,{recursive:true});
 const rows=['2026-09-30','2026-10-16'].map((date,i)=>({record_id:`demo-${tier}-${i}`,source:'codex',provider:'demo',model:'fixture',occurred_at:date+'T12:00:00+08:00',input_tokens:total*(i?.4:.6)-100,output_tokens:100,granularity:'request_delta'}));
 const records=path.join(folder,'input.jsonl');fs.writeFileSync(records,rows.map(r=>JSON.stringify(r)).join('\n'));
 const result=cli(['run','--sources','none','--no-history','--import-records',records,'--month','2026-08','--out',folder]);
 return result.report;
}
(async()=>{
 const reports=Array.from({length:5},(_,i)=>makeReport(i+1));
 const empty=cli(['scan','--sources','none','--out',path.join(out,'empty')]);
 const browser=await chromium.launch({headless:true,...(process.env.TOKENME_BROWSER?{executablePath:process.env.TOKENME_BROWSER}:{})});
 try{
  const page=await browser.newPage({viewport:{width:1360,height:1000}}),errors=[],network=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url()))network.push(r.url());});
  let cases=0;
  for(let i=0;i<reports.length;i++){
   await page.goto(pathToFileURL(reports[i]).href);assert.equal(await page.inputValue('#card-style'),'cyber');
   assert.equal(await page.isDisabled('#export-card'),false);
   for(const style of ['cyber','paper'])for(const period of ['all','2026-10'])for(const format of ['portrait','square'])for(const qr of [false,true]){
    await page.selectOption('#card-style',style);await page.selectOption('#share-period',period);await page.selectOption('#card-format',format);await page.locator('#include-qr').setChecked(qr);
    const state=await page.evaluate(()=>{
     const m=TokenMeCard.modelFor(data,$('nickname').value,$('share-period').value),c=$('card'),x=c.getContext('2d');
     let exact=true;
     if($('include-qr').checked){const matrix=data.share.matrix,size=(matrix.length+8)*4,sx=1008-size,sy=c.height-80-size;
      for(let iy=0;iy<matrix.length+8;iy++)for(let ix=0;ix<matrix.length+8;ix++){
       const bit=iy>=4&&iy<matrix.length+4&&ix>=4&&ix<matrix.length+4?matrix[iy-4][ix-4]:'0';const p=x.getImageData(sx+ix*4+2,sy+iy*4+2,1,1).data;
       if(bit==='1'?p[0]>30||p[1]>50||p[2]>40:p[0]!==255||p[1]!==255||p[2]!==255)exact=false;
      }
     }
     return {total:m.total,level:m.level.number,width:c.width,height:c.height,exact,grade:$('share-grade').textContent,alt:$('card-preview').alt};
    });
    assert.equal(state.level,i+1);assert.equal(state.width,1080);assert.equal(state.height,format==='square'?1080:1440);assert.equal(state.exact,true);
    assert.match(state.grade,new RegExp(`L${i+1}`));assert.match(state.alt,/分享图/);cases++;
   }
   await page.selectOption('#card-style','cyber');
   await page.fill('#nickname','很长的昵称用于检查正式报告里的分享输出');
   const before=await page.locator('#card').evaluate(c=>c.toDataURL().split(',')[1]);
   const wait=page.waitForEvent('download');await page.click('#export-card');const download=await wait;
   const target=path.join(out,`L${i+1}-monthly-square.png`);await download.saveAs(target);assert.equal(await download.failure(),null);
   assert.deepEqual(fs.readFileSync(target),Buffer.from(before,'base64'));
   await page.selectOption('#share-period','2026-08');assert.equal(await page.isDisabled('#export-card'),true);assert.equal(await page.isVisible('#card-preview'),true);
   assert.match(await page.locator('#share-empty').textContent(),/暂无有效记录/);
  }
  await page.goto(pathToFileURL(reports[4]).href);await page.setViewportSize({width:360,height:900});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.locator('#share-title').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,'mobile-share.png'),fullPage:true});
  await page.goto(pathToFileURL(empty.report).href);assert.equal(await page.isDisabled('#export-card'),true);assert.equal(await page.isVisible('#card-preview'),true);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  const placeholder=await page.locator('#card').evaluate(c=>c.toDataURL().split(',')[1]);fs.writeFileSync(path.join(out,'empty-card.png'),Buffer.from(placeholder,'base64'));
  assert.deepEqual(errors,[]);assert.deepEqual(network,[]);
  console.log(JSON.stringify({cases,downloads:5,pixelEquality:true,emptyExportsDisabled:true,mobileWidth:360,networkRequests:0,pageErrors:0}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
