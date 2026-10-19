/* Design study 02. Native Canvas + the existing TokenMe model. Synthetic data only. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id), canvas = $('card'), ctx = canvas.getContext('2d');
  const daily = Array.from({length:24}, (_, i) => ({date:`2026-09-${String(i+7).padStart(2,'0')}`, total_tokens:12840000+(i%5)*250000}));
  const total = daily.reduce((sum, day) => sum + day.total_tokens, 0);
  const bundle = {generated_at:'2026-09-30T12:00:00Z', views:{all:{total_tokens:total, active_days:24,
    timezone:'UTC+08:00', first_observed_day:daily[0].date, last_observed_day:daily.at(-1).date, daily,
    sources:[{source:'codex',total_tokens:total*0.7},{source:'claude',total_tokens:total*0.3}]}}};
  const palettes = {spectral:[178,205,252,290,327],ion:[80,123,164,190,226],ember:[27,8,335,302,268]};
  function text(value,x,y,size,color='#eef1ff',weight=400,width=936,align='left') {
    ctx.textAlign=align;ctx.fillStyle=color;
    const font=()=>{ctx.font=`${weight} ${size}px "Segoe UI", "Microsoft YaHei", sans-serif`;};font();
    while(ctx.measureText(value).width>width && size>22){size--;font();}
    let chars=Array.from(String(value));
    while(ctx.measureText(chars.join('')).width>width && chars.length>1){chars.splice(-2,2,'…');}
    ctx.fillText(chars.join(''),x,y);
  }
  function rule(y){ctx.strokeStyle='#353b57';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(72,y);ctx.lineTo(1008,y);ctx.stroke();}
  function hueAt(t){const hues=palettes[$('palette').value],p=Math.max(0,Math.min(.9999,t))*(hues.length-1),i=Math.floor(p);return hues[i]+(hues[i+1]-hues[i])*(p-i);}
  // A continuous 4D parametric surface, rotated through XW and YZ planes,
  // then projected to 3D and 2D. Disorder deforms the same surface smoothly.
  function point(u,v,chaos,rhythm){
    const warp=chaos*(.16*Math.sin(5*u+3*v)+.10*Math.cos(9*u-2*v));
    const radius=2.03+.73*Math.cos(v)+warp;
    let x=radius*Math.cos(u),y=radius*Math.sin(u),z=.85*Math.sin(v)+chaos*.26*Math.sin(3*u+2*v);
    let w=.75*Math.sin(2*u+v)+.13*rhythm*Math.cos(5*u-v);
    const a=.59,b=.95,c=-.48;
    [x,w]=[x*Math.cos(a)-w*Math.sin(a),x*Math.sin(a)+w*Math.cos(a)];
    [y,z]=[y*Math.cos(b)-z*Math.sin(b),y*Math.sin(b)+z*Math.cos(b)];
    [x,y]=[x*Math.cos(c)-y*Math.sin(c),x*Math.sin(c)+y*Math.cos(c)];
    const p4=4.3/(4.3-w),p3=7/(7-z*p4);
    return {x:x*p4*p3,y:y*p4*p3,z};
  }
  function art(cx,cy,scale,chaos,rhythm){
    ctx.save();ctx.translate(cx,cy);ctx.scale(scale,scale);
    const haze=ctx.createRadialGradient(10,0,20,10,0,420);haze.addColorStop(0,'#6243db17');haze.addColorStop(.6,'#1552aa0c');haze.addColorStop(1,'#090b1400');ctx.fillStyle=haze;ctx.fillRect(-510,-380,1020,760);
    let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
    for(let j=0;j<40;j++)for(let k=0;k<160;k++){
      const p=point(k/160*Math.PI*2,j/40*Math.PI*2,chaos,1);
      minX=Math.min(minX,p.x*126);maxX=Math.max(maxX,p.x*126);minY=Math.min(minY,p.y*126);maxY=Math.max(maxY,p.y*126);
    }
    const fit=Math.min(920/(maxX-minX),510/(maxY-minY));
    ctx.scale(fit,fit);ctx.translate(-(minX+maxX)/2,-(minY+maxY)/2);
    ctx.globalCompositeOperation='lighter';
    const rows=112,steps=280;
    for(let j=0;j<rows;j++){
      const v=j/rows*Math.PI*2,r=rhythm[Math.floor(j/rows*rhythm.length)]||.5;
      let prev=point(0,v,chaos,r);
      for(let k=1;k<=steps;k++){
        const u=k/steps*Math.PI*2,p=point(u,v,chaos,r),depth=Math.max(0,Math.min(1,(p.z+1.2)/2.4));
        const hue=hueAt((j/rows*.48+k/steps*.52)%1);
        ctx.strokeStyle=`hsla(${hue},95%,${54+depth*12}%,${.16+depth*.37})`;
        ctx.lineWidth=.7+Math.max(0,depth)*.65;
        ctx.beginPath();ctx.moveTo(prev.x*126,prev.y*126);ctx.lineTo(p.x*126,p.y*126);ctx.stroke();prev=p;
      }
    }
    // Sparse cross-sections expose the geometry without a wireframe cage.
    for(let j=0;j<12;j++){
      ctx.beginPath();for(let k=0;k<=160;k++){const p=point(j/12*Math.PI*2,k/160*Math.PI*2,chaos,.5);if(k===0)ctx.moveTo(p.x*126,p.y*126);else ctx.lineTo(p.x*126,p.y*126);}
      ctx.strokeStyle=`hsla(${hueAt(j/12)},90%,75%,.17)`;ctx.lineWidth=.7;ctx.stroke();
    }
    ctx.restore();
  }
  function draw(){
    const square=$('format').value==='square',h=square?1080:1440,chaos=Number($('chaos').value)/100;
    $('amount').textContent=Math.round(chaos*100)+'%';
    const m=TokenMeCard.modelFor(bundle,$('nickname').value);
    canvas.width=1080;canvas.height=h;
    ctx.fillStyle='#080b14';ctx.fillRect(0,0,1080,h);
    const bg=ctx.createLinearGradient(0,0,1080,h);bg.addColorStop(0,'#22214640');bg.addColorStop(.5,'#080b1400');bg.addColorStop(1,'#07342d30');ctx.fillStyle=bg;ctx.fillRect(0,0,1080,h);
    // Fixed subtle grain; repeated export is pixel-stable.
    let seed=7;for(let i=0;i<12000;i++){seed=(seed*1664525+1013904223)>>>0;const x=seed%1080;seed=(seed*1664525+1013904223)>>>0;ctx.fillStyle=i%2?'#ffffff06':'#00000016';ctx.fillRect(x,seed%h,1,1);}
    text('TokenMe',72,105,43,'#f4f3ff',600);text(m.stamp,1008,103,28,'#a6b0c9',400,260,'right');
    rule(137);text(m.nickname,72,202,38,'#d7def5',400,590);text(`累计 L${m.level.number}`,1008,201,29,'#bcadff',500,280,'right');
    // Art is clipped to its own field, leaving data and identity legible.
    ctx.save();ctx.beginPath();ctx.rect(38,224,1004,square?330:568);ctx.clip();
    art(540,square?393:505,square?.59:1.02,chaos,m.rhythm);ctx.restore();
    const labelY=square?595:838,numberY=square?705:978;
    text('累计 I 量',72,labelY,30,'#aeb9d4');text(m.value,65,numberY,square?112:142,'#f3f5ff',300,780);
    ctx.font=`300 ${square?112:142}px "Segoe UI",sans-serif`;const nw=ctx.measureText(m.value).width;
    text('I',Math.min(65+nw+24,900),numberY,48,'#9dabcd',300,60);
    text(m.total.toLocaleString('en-US')+' TOKENS',76,numberY+48,25,'#8e9dbd');
    const ry=square?786:1070;rule(ry);
    text(m.collaboration.stage,72,ry+61,39,'#eeeaff',500);
    text(m.collaboration.evidence,72,ry+109,27,'#c0cbe3');
    text(`截至 ${m.collaboration.through} · 依据本地记录评估`,72,ry+151,23,'#8999b9');
    const footer=square?1002:1310;
    text(`${m.activeDays} 活跃日 · ${m.tools}`,72,footer,27,'#b3c0db');
    text(`${m.range} · 本地记录 · 含缓存`,72,footer+42,23,'#8291ad');
    const edge=ctx.createLinearGradient(0,0,1080,0);for(let i=0;i<5;i++)edge.addColorStop(i/4,`hsl(${hueAt(i/4)},90%,65%)`);ctx.fillStyle=edge;ctx.fillRect(72,h-21,936,2);
    canvas.setAttribute('aria-label',`${m.nickname}，累计 ${m.value} I，${m.collaboration.stage}。合成示例数据。`);
  }
  let frame;for(const id of ['nickname','palette','chaos','format'])$(id).addEventListener('input',()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(draw);});
  $('save').addEventListener('click',()=>{draw();canvas.toBlob(blob=>{if(!blob){$('status').textContent='生成失败，请重试。';return;}const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`tokenme-cyber-${$('palette').value}-${$('format').value}.png`;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);$('status').textContent='PNG 已生成。';},'image/png');});
  draw();
})();
