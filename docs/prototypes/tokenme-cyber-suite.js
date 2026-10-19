/* Interactive design review. Synthetic data supplied separately. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id),canvas=$('card');
  function selection(){return {tier:Number($('tier').value),scenario:$('scenario').value,period:$('period').value,nickname:$('nickname').value};}
  function modelFor({tier=3,scenario='sustained',period='all',nickname='我的 AI 足迹'}={}){
    const bundle=TokenMeCyberDemo.bundleFor(tier,scenario);
    const scope=scenario==='empty'?'2026-10':period;
    const m=TokenMeCard.modelFor(bundle,nickname,scope);
    if(!m.available){m.nickname=String(nickname).trim()||'我的 AI 足迹';m.stamp='2026.10';}
    return m;
  }
  function render(){
    const s=selection(),m=modelFor(s),theme=TokenMeCyber.themes[s.tier-1];
    $('theme-title').textContent=`L${s.tier} · ${theme.name}`;$('theme-description').textContent=theme.caption;
    $('amount').textContent=$('chaos').value+'%';
    if(s.scenario==='empty')$('period').value='2026-10';
    $('period').disabled=s.scenario==='empty';
    TokenMeCyber.draw(canvas,m,$('format').value,{chaos:Number($('chaos').value)/100,qr:$('qr').checked?TokenMeCyberDemo.qr:null,state:s.scenario});
    $('save').disabled=!m.available;$('status').textContent=m.available?'':m.message;
    document.querySelectorAll('.tile').forEach(el=>el.setAttribute('aria-pressed',String(Number(el.dataset.tier)===s.tier)));
    return m;
  }
  function save(c,name){c.toBlob(blob=>{if(!blob){$('status').textContent='图片生成失败，请重试。';return;}const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);$('status').textContent='PNG 已生成。';},'image/png');}
  function overview(){
    const c=document.createElement('canvas');c.width=2400;c.height=940;const x=c.getContext('2d');x.fillStyle='#080b14';x.fillRect(0,0,c.width,c.height);
    x.fillStyle='#edf0ff';x.font='500 50px "Segoe UI","Microsoft YaHei",sans-serif';x.fillText('TokenMe / 混沌涌现',60,86);
    x.fillStyle='#91a1bf';x.font='24px "Segoe UI","Microsoft YaHei",sans-serif';x.fillText('五档视觉套系 · 合成示例数据 · 累计等级与使用习惯分别计算',60,134);
    for(let i=0;i<5;i++){
      const card=document.createElement('canvas'),theme=TokenMeCyber.themes[i];TokenMeCyber.draw(card,modelFor({tier:i+1}),'portrait',{qr:TokenMeCyberDemo.qr});
      x.drawImage(card,60+i*462,180,432,576);x.fillStyle='#e7eaff';x.font='30px "Segoe UI","Microsoft YaHei",sans-serif';x.fillText(`L${i+1} / ${theme.name}`,60+i*462,817);
      x.fillStyle='#91a1bf';x.font='22px "Segoe UI","Microsoft YaHei",sans-serif';x.fillText(theme.caption,60+i*462,860);
    }return c;
  }
  for(let i=0;i<5;i++){
    const theme=TokenMeCyber.themes[i],tile=document.createElement('button');tile.className='tile';tile.type='button';tile.dataset.tier=i+1;
    tile.setAttribute('aria-label',`选择 L${i+1} ${theme.name}`);
    const thumb=document.createElement('canvas');TokenMeCyber.draw(thumb,modelFor({tier:i+1}),'portrait');
    const title=document.createElement('strong');title.textContent=`L${i+1} · ${theme.name}`;
    const caption=document.createElement('small');caption.textContent=theme.caption;
    tile.append(thumb,title,caption);tile.addEventListener('click',()=>{$('tier').value=String(i+1);render();});$('gallery').append(tile);
  }
  let frame;for(const id of ['tier','scenario','period','format','nickname','chaos','qr'])$(id).addEventListener('input',()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(render);});
  $('grayscale').addEventListener('change',()=>{for(const c of document.querySelectorAll('canvas'))c.style.filter=$('grayscale').checked?'grayscale(1)':'none';});
  $('save').addEventListener('click',()=>{const m=render();if(m.available)save(canvas,`TokenMe-cyber-L${m.level.number}-${m.scope}-${$('format').value}-${$('qr').checked?'qr':'clean'}.png`);});
  $('overview').addEventListener('click',()=>save(overview(),'TokenMe-cyber-collection.png'));
  window.TokenMeSuite={modelFor,render,overview};render();
})();
