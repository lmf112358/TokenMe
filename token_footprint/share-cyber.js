/* TokenMe cyber collection. Original native Canvas artwork; no third-party runtime. */
(function(root){
  'use strict';
  const themes = [
    {name:'初光',caption:'单核 · 一束游离的光',hues:[183,212,249,172,298],rotation:[.43,.80,-.60],phase:-.25,bands:1,lanes:38,extent:.72,warp:.28,shell:0},
    {name:'脉冲',caption:'双轨 · 两股交汇的能量',hues:[79,128,182,238,302],rotation:[.69,1.04,-.20],phase:.35,bands:2,lanes:34,extent:.85,warp:.48,shell:0},
    {name:'交织',caption:'多层 · 三维编织的核心',hues:[182,252,316,338,82],rotation:[.59,.95,-.48],phase:0,bands:4,lanes:32,extent:.96,warp:1,shell:0},
    {name:'裂变',caption:'裂隙 · 核心与轨道分离',hues:[24,350,321,277,41],rotation:[.35,1.17,-.72],phase:.60,bands:5,lanes:32,extent:1,warp:1.15,shell:1},
    {name:'涌现',caption:'全域 · 核心与高维场相连',hues:[272,310,183,54,85],rotation:[.74,.67,-.35],phase:1.1,bands:5,lanes:38,extent:1,warp:1.2,shell:2}
  ];
  function draw(canvas,model,format='portrait',options={}){
    const square=format==='square',h=square?1080:1440;
    canvas.width=1080;canvas.height=h;
    const ctx=canvas.getContext('2d');
    if(!ctx)throw new Error('当前浏览器不支持 Canvas');
    const m=model||{},theme=themes[Math.max(0,Math.min(4,(m.level?.number||1)-1))];
    const chaos=Number.isFinite(options.chaos)?Math.max(0,Math.min(1,options.chaos)):.82;
    const qr=options.qr?.matrix;
    const hasQR=Array.isArray(qr)&&qr.length>=21&&qr.length<=37&&qr.every(row=>typeof row==='string'&&row.length===qr.length&&/^[01]+$/.test(row));
  function text(value,x,y,size,color='#eef1ff',weight=400,width=936,align='left') {
    ctx.textAlign=align;ctx.fillStyle=color;
    const font=()=>{ctx.font=`${weight} ${size}px "Segoe UI", "Microsoft YaHei", sans-serif`;};font();
    while(ctx.measureText(value).width>width && size>22){size--;font();}
    let chars=Array.from(String(value));
    while(ctx.measureText(chars.join('')).width>width && chars.length>1){chars.splice(-2,2,'…');}
    ctx.fillText(chars.join(''),x,y);
  }
  function rule(y){ctx.strokeStyle='#353b57';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(72,y);ctx.lineTo(1008,y);ctx.stroke();}
  // A continuous 4D parametric surface, rotated through XW and YZ planes,
  // then projected to 3D and 2D. Disorder deforms the same surface smoothly.
  function point(u,v,chaos,rhythm){
    const warp=chaos*(.37*Math.sin(3*u+2*v)+.19*Math.cos(7*u-v));
    const radius=1.85+.72*Math.cos(v)+warp;
    let x=radius*Math.cos(u),y=radius*Math.sin(u),z=.95*Math.sin(v)+chaos*.44*Math.sin(3*u+2*v);
    let w=.85*Math.sin(2*u+v)+.19*rhythm*Math.cos(5*u-v);
    const [a,b,c]=theme.rotation;
    [x,w]=[x*Math.cos(a)-w*Math.sin(a),x*Math.sin(a)+w*Math.cos(a)];
    [y,z]=[y*Math.cos(b)-z*Math.sin(b),y*Math.sin(b)+z*Math.cos(b)];
    [x,y]=[x*Math.cos(c)-y*Math.sin(c),x*Math.sin(c)+y*Math.cos(c)];
    const p4=4.3/(4.3-w),p3=7/(7-z*p4);
    return {x:x*p4*p3,y:y*p4*p3,z};
  }
  function art(cx,cy,scale,chaos,rhythm){
    ctx.save();ctx.translate(cx,cy);ctx.scale(scale*(square?1.32:1),scale);
    const hues=theme.hues;
    const tier=m.available?m.level.number:1;
    for(const [x,y,hue] of [[-140,-30,hues[0]],[160,35,hues[2]]]){
      const haze=ctx.createRadialGradient(x,y,4,x,y,310);
      haze.addColorStop(0,`hsla(${hue},100%,45%,${.025+tier*.025})`);haze.addColorStop(1,`hsla(${hue},100%,20%,0)`);
      ctx.fillStyle=haze;ctx.fillRect(-510,-280,1020,560);
    }
    // Open, nonuniform fibers share a 4D field. They diverge locally and
    // reconverge; no cross-sectional lattice or independent random scribbles.
    const paths=[];
    let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
    const rows=theme.bands*theme.lanes,steps=350;
    for(let j=0;j<rows;j++){
      const group=Math.floor(j/theme.lanes),lane=j%theme.lanes;
      const phase=group*(tier===2?Math.PI:1.27)+lane*.022+theme.phase;
      const escape=tier>=3&&j%17===0,r=rhythm[j%rhythm.length]??.5;
      const start=.28*Math.sin(lane*.09+group)+group*.37;
      const length=Math.PI*(tier===1?1.83:tier===2?2:1.55+(Math.sin(lane*.065+group)+1)*.30);
      const points=[];let depth=0;
      for(let k=0;k<=steps;k++){
        const t=k/steps,u=start+t*length;
        const envelope=Math.pow(Math.sin(Math.PI*t),2);
        const deformation=chaos*theme.warp;
        const drift=deformation*(.68*Math.sin(u*2+phase)+.36*Math.sin(u*3.7+lane*.045+group));
        const v=phase+drift+deformation*.13*Math.sin(u*8+lane*.08)*envelope;
        const p=point(u,v,deformation,r);
        const excursion=escape?1+deformation*.40*envelope:1;
        p.x=p.x*126*excursion;p.y=p.y*107*excursion;
        points.push(p);depth+=p.z;
        minX=Math.min(minX,p.x);maxX=Math.max(maxX,p.x);minY=Math.min(minY,p.y);maxY=Math.max(maxY,p.y);
      }
      paths.push({points,group,j,escape,depth:depth/(steps+1)});
    }
    // Fit the actual generated paths, including escaping fibers.
    const fit=Math.min(950/(maxX-minX),520/(maxY-minY))*theme.extent*(theme.shell===2?.66:theme.shell===1?.76:1);
    const midX=(minX+maxX)/2,midY=(minY+maxY)/2;
    // The shell is a separate depth layer, with a silhouette readable without color.
    function orbit(angle,rx,ry,phase,alpha,width){
      ctx.save();ctx.rotate(angle);ctx.strokeStyle=`hsla(${hues[phase%5]},100%,65%,${alpha})`;ctx.lineWidth=width;ctx.beginPath();
      for(let k=0;k<=240;k++){
        const u=k/240*Math.PI*2,ripple=1+.027*chaos*Math.sin(7*u+phase);
        const x=Math.cos(u)*rx*ripple,y=Math.sin(u)*ry*ripple;
        k?ctx.lineTo(x,y):ctx.moveTo(x,y);
      }ctx.stroke();ctx.restore();
    }
    if(theme.shell===1){
      for(let plane=0;plane<3;plane++)for(let line=0;line<6;line++)orbit(-.6+plane*.65,350+line*2,88+line*3,plane,.27+line*.055,line===5?1.9:.9);
      // Projected fragments expose breaks between the core and surrounding planes.
      for(let i=0;i<7;i++){
        const a=i*.9,x=Math.cos(a)*330,y=Math.sin(a)*210;
        ctx.strokeStyle=`hsla(${hues[i%5]},100%,68%,.55)`;ctx.lineWidth=1.2;
        ctx.beginPath();ctx.moveTo(x-12,y+7);ctx.lineTo(x+16,y-5);ctx.lineTo(x+4,y-23);ctx.stroke();
      }
    }
    if(theme.shell===2){
      // Multiple projected meridians enclose a volumetric field around the chaotic core.
      for(let i=0;i<28;i++){
        const a=i/28*Math.PI;orbit(-.20,405*Math.cos(a),245,Math.floor(i/6),.23+(i%6)*.035,.9);
      }
      for(let i=1;i<9;i++){
        const latitude=(i/9-.5)*Math.PI,r=Math.cos(latitude),y=Math.sin(latitude)*245;
        ctx.save();ctx.translate(0,y);orbit(-.20,405*r,28*r,i,.28,.9);ctx.restore();
      }
      orbit(-.20,410,248,3,.70,1.7);
    }
    paths.sort((a,b)=>a.depth-b.depth);
    ctx.lineCap='round';ctx.lineJoin='round';
    for(const path of paths){
      const {points,group,j,escape}=path,hue=hues[tier===2?group*2:group];
      const depth=Math.max(0,Math.min(1,(path.depth+1)/2));
      const gradient=ctx.createLinearGradient(-400,-220,400,240);
      gradient.addColorStop(0,`hsla(${hue-16},100%,53%,.12)`);
      gradient.addColorStop(.28,`hsla(${hue},100%,57%,${.55+depth*.35})`);
      gradient.addColorStop(.72,`hsla(${hue+12},100%,60%,.93)`);
      gradient.addColorStop(1,`hsla(${hue+26},100%,50%,.15)`);
      ctx.beginPath();
      points.forEach((p,k)=>{const x=(p.x-midX)*fit,y=(p.y-midY)*fit;k?ctx.lineTo(x,y):ctx.moveTo(x,y);});
      ctx.globalCompositeOperation='source-over';ctx.strokeStyle=gradient;
      ctx.lineWidth=escape?1.5:.65+(j%7)/7*1.05;
      // A few substantial light filaments give depth; fine fibers keep color.
      if(j%13===0){ctx.shadowColor=`hsl(${hue},100%,55%)`;ctx.shadowBlur=4+tier*2;ctx.lineWidth=2.1+tier*.12;}
      ctx.stroke();ctx.shadowBlur=0;
      if(escape){
        const p=points[Math.floor(steps*.63)],x=(p.x-midX)*fit,y=(p.y-midY)*fit;
        ctx.fillStyle=`hsla(${hue},100%,80%,.9)`;ctx.beginPath();ctx.arc(x,y,1.9,0,Math.PI*2);ctx.fill();
      }
    }
    if(theme.shell===2){
      // Foreground arcs and radial connections weave the core into the outer field.
      orbit(.25,395,142,2,.55,1.5);orbit(-.65,310,137,3,.65,1.6);
      for(let i=0;i<16;i++){
        const a=i/16*Math.PI*2,x=Math.cos(a)*405,y=Math.sin(a)*242;
        ctx.strokeStyle=`hsla(${hues[i%5]},100%,68%,.24)`;ctx.lineWidth=.8;
        ctx.beginPath();ctx.moveTo(x*.56,y*.56);ctx.quadraticCurveTo(x*.95-30,y*.65,x,y);ctx.stroke();
        ctx.fillStyle=`hsla(${hues[i%5]},100%,80%,.85)`;ctx.beginPath();ctx.arc(x,y,2.2,0,Math.PI*2);ctx.fill();
      }
    }
    ctx.restore();
  }

    ctx.fillStyle='#080b14';ctx.fillRect(0,0,1080,h);
    const bg=ctx.createLinearGradient(0,0,1080,h);
    bg.addColorStop(0,`hsla(${theme.hues[1]},65%,18%,.20)`);bg.addColorStop(.5,'#080b1400');bg.addColorStop(1,`hsla(${theme.hues[0]},65%,12%,.15)`);
    ctx.fillStyle=bg;ctx.fillRect(0,0,1080,h);
    let seed=7;for(let i=0;i<12000;i++){seed=(seed*1664525+1013904223)>>>0;const x=seed%1080;seed=(seed*1664525+1013904223)>>>0;ctx.fillStyle=i%2?'#ffffff06':'#00000016';ctx.fillRect(x,seed%h,1,1);}
    text('TokenMe',72,105,43,'#f4f3ff',600);text(m.stamp||'等待记录',1008,103,28,'#a6b0c9',400,260,'right');
    rule(137);text(m.nickname||'我的 AI 足迹',72,202,38,'#d7def5',400,555);
    if(!m.available){
      const states={unconnected:['尚未接入','连接你的 AI 工具，开始留下足迹。','未接入不代表零用量。'],zero:['等待第一束光','已接入，尚无有效用量记录。','累计用量为 0，暂未评级。'],empty:['这个月，留白','当月暂无有效记录。','选择其他月份，或查看累计档案。']};
      const state=states[options.state]||['记录暂不可用',m.message||'请检查记录后重试。','没有足够的数据生成分享卡。'];
      ctx.save();ctx.globalAlpha=.34;
      art(540,square?390:500,square?.55:.86,.35,[]);ctx.restore();
      text(state[0],72,square?640:900,64,'#f0efff',400);
      text(state[1],72,square?710:980,32,'#bdc8df');
      rule(square?780:1070);text(state[2],72,square?840:1136,27,'#91a2c2');
      text('连接 · 记录 · 看见自己的 AI 足迹',72,h-100,28,'#9baac6');
      canvas.setAttribute?.('aria-label',state.join('。'));return canvas;
    }
    text(`累计 L${m.level.number} · ${theme.name}`,1008,201,29,'#c9baff',500,345,'right');
    // A compact five-step marker reinforces hierarchy at thumbnail size.
    for(let i=0;i<5;i++){
      ctx.fillStyle=i<m.level.number?`hsl(${theme.hues[0]},95%,68%)`:'#283048';
      ctx.fillRect(888+i*25,216,18,4);
    }
    ctx.save();ctx.beginPath();ctx.rect(38,224,1004,square?330:568);ctx.clip();
    art(540,square?393:505,square?.59:1.02,chaos,m.rhythm||[]);ctx.restore();
    const labelY=square?595:838,numberY=square?705:978;
    text(m.label,72,labelY,30,'#aeb9d4');
    let size=square?112:142;const value=String(m.value);
    const setFont=()=>{ctx.font=`300 ${size}px "Segoe UI", "Microsoft YaHei", sans-serif`;};setFont();
    while(ctx.measureText(value).width>820&&size>40){size--;setFont();}
    const numberWidth=ctx.measureText(value).width;
    text(value,65,numberY,size,'#f3f5ff',300,820);
    text('I',65+numberWidth+24,numberY,48,'#9dabcd',300,60);
    text(m.total.toLocaleString('en-US')+' TOKENS',76,numberY+48,25,'#8e9dbd');
    const ry=square?786:1070,width=hasQR?710:936,c=m.collaboration;
    rule(ry);text(c.stage,72,ry+61,39,'#eeeaff',500,width);
    text(c.evidence,72,ry+109,27,'#c0cbe3',400,width);
    text(c.available?`截至 ${c.through} · 依据本地记录评估`:'日期资料不足 · 依据本地记录评估',72,ry+151,23,'#8999b9',400,width);
    const footer=square?1002:1310;
    text(`${m.activeDays} 活跃日 · ${m.tools||'工具未提供'}`,72,footer,27,'#b3c0db',400,width);
    text(`${m.range} · 本地记录 · 含缓存`,72,footer+42,23,'#8291ad',400,width);
    if(hasQR){
      const cell=4,size=(qr.length+8)*cell,x=1008-size,y=h-80-size;
      ctx.fillStyle='#ffffff';ctx.fillRect(x,y,size,size);ctx.fillStyle='#080b14';
      qr.forEach((row,iy)=>Array.from(row).forEach((bit,ix)=>{if(bit==='1')ctx.fillRect(x+(ix+4)*cell,y+(iy+4)*cell,cell,cell);}));
      text('生成我的',x+size/2,h-40,26,'#b3c0db',400,size,'center');
    }
    const edge=ctx.createLinearGradient(0,0,1080,0);for(let i=0;i<5;i++)edge.addColorStop(i/4,`hsl(${theme.hues[i]},90%,65%)`);ctx.fillStyle=edge;ctx.fillRect(72,h-21,936,2);
    canvas.setAttribute?.('aria-label',`${m.nickname}，${m.label} ${m.value} I，累计 L${m.level.number} ${theme.name}，${c.stage}。`);
    return canvas;
  }
  const api={themes,draw};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.TokenMeCyber=api;
})(typeof globalThis!=='undefined'?globalThis:this);
