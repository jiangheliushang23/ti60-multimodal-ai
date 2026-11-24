"use strict";
(() => {
 const el=id=>document.getElementById(id),ns='http://www.w3.org/2000/svg';let active='live',busy=false,offset=0;
 const fmt=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
 function streaming(on){const img=el('mobile-picture');if(on&&!img.getAttribute('src'))img.src='/stream.mjpg';if(!on)img.removeAttribute('src');}
 for(const button of document.querySelectorAll('[data-select]'))button.onclick=()=>{active=button.dataset.select;for(const page of document.querySelectorAll('[data-tab]'))page.hidden=page.dataset.tab!==active;for(const item of document.querySelectorAll('[data-select]'))item.classList.toggle('selected',item===button);streaming(active==='live'&&!document.hidden);};
 document.addEventListener('visibilitychange',()=>streaming(active==='live'&&!document.hidden));
 el('mobile-zoom').onclick=()=>{const card=el('mobile-stage').closest('.panel');card.classList.toggle('mobile-zoomed');el('mobile-zoom').textContent=card.classList.contains('mobile-zoomed')?'缩小':'放大';};
 function boxes(people){const svg=el('mobile-boxes');svg.replaceChildren();for(const p of people){const [x1,y1,x2,y2]=p.box,color=p.alarm?'#ff4444':'#45ec95',r=document.createElementNS(ns,'rect'),label=document.createElementNS(ns,'text');for(const [k,v] of Object.entries({x:x1,y:y1,width:x2-x1,height:y2-y1,fill:'none',stroke:color,'stroke-width':5}))r.setAttribute(k,v);label.setAttribute('x',x1);label.setAttribute('y',Math.max(30,y1-10));label.setAttribute('fill',color);label.setAttribute('font-size',32);label.setAttribute('font-weight',700);label.textContent=`ID ${p.id}${p.alarm?' 跌倒':''}`;svg.append(r,label);}}
 function render(s){
  const a=s.smart_assist,t=s.status,online=s.online,now=Date.now();if(a)offset=Date.parse(a.server_time)-now;clock();
  el('mobile-online').textContent=online?'板端在线':'板端离线';el('mobile-online').className='pill '+(online?'ok':'off');
  const env=online&&t.environment_valid,ir=online&&t.infrared_valid;
  el('mobile-temperature').textContent=env?t.temperature_c.toFixed(1):'—';el('mobile-humidity').textContent=env?t.humidity_percent.toFixed(1):'—';el('mobile-ir').textContent=ir?t.ir_max_c.toFixed(1):'—';
  const fresh=online&&t.power_mode!==2&&((t.device_ms-t.capture_ms)>>>0)<=1500,people=fresh?t.people.filter(p=>p.valid&&p.id):[];
  el('mobile-people').textContent=online?people.length:'—';el('mobile-power').textContent=online?(t.power_mode===2?'低功耗 · 红外监测':'正常检测'):'等待板端';boxes(people);
  const falling=people.filter(p=>p.alarm);el('mobile-alarm-title').textContent=!online?'板端已离线':falling.length?'检测到跌倒':'当前无跌倒报警';el('mobile-alarm-note').textContent=falling.length?falling.map(p=>`人物 ID ${p.id}`).join('、')+' · 红框保持，直到同一人物重新站起':online?'持续监测两个人体，分别判断跌倒':'请检查开发板供电、网线和电脑接收服务';el('mobile-alarm-title').closest('article').classList.toggle('alert',Boolean(falling.length));
  el('mobile-resolution').textContent=s.image?`${s.image.width} × ${s.image.height} · ${s.received_image_hz.toFixed(1)} FPS`:'等待视频';el('mobile-video-note').textContent=s.image_age_ms!=null&&s.image_age_ms<3000?'摄像头实时彩色画面 · 框为最近一次有效推理结果':'画面已过期，不能用于判断现场状态';
  if(a){const advice=a.advice;el('mobile-advice').textContent=advice.mode+(advice.setpoint_c!=null?` · ${advice.setpoint_c}°C`:'')+(advice.fan?' · '+advice.fan:'');el('mobile-advice-note').textContent=advice.reason;}
  const rows=[...(s.events||[]).filter(e=>e.type==='fall').map(e=>({time:e.received_at,title:'跌倒报警',text:`人物 ID ${e.person.id} · 人体检测分数 ${(e.person.score_q15*100/32768).toFixed(1)}%` })),...(a?.events||[]).map(e=>({time:e.received_at,title:'非授权时段人体出现',text:`人物 ID ${e.person_id} · ${e.voice_detail}`}))].sort((x,y)=>Date.parse(y.time)-Date.parse(x.time));
  const list=el('mobile-events');list.replaceChildren();for(const row of rows.slice(0,60)){const item=document.createElement('div'),title=document.createElement('strong'),time=document.createElement('time'),p=document.createElement('p');item.className='mobile-event';title.textContent=row.title;time.textContent=fmt.format(new Date(row.time));p.textContent=row.text;item.append(title,time,p);list.append(item);}if(!rows.length)list.textContent='暂无异常事件';
 }
 async function poll(){if(busy||document.hidden)return;busy=true;try{const r=await fetch('/api/status',{cache:'no-store'});if(!r.ok)throw Error();render(await r.json());}catch(_){el('mobile-online').textContent='服务连接中断';el('mobile-online').className='pill off';for(const id of ['mobile-temperature','mobile-humidity','mobile-ir','mobile-people'])el(id).textContent='—';boxes([]);}finally{busy=false;}}
 function clock(){el('mobile-clock').textContent=fmt.format(new Date(Date.now()+offset))+' · 北京时间';}
 clock();setInterval(clock,1000);streaming(true);poll();setInterval(poll,750);
})();
