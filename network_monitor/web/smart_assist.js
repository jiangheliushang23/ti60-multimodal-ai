"use strict";
(() => {
 const el=id=>document.getElementById(id);let busy=false,loaded=false,offset=0,periodCount=0;
 const dateFormat=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',weekday:'long',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
 const voiceNames={pending:'等待语音',queued:'板端已接受',module_completed:'模块确认播放完成',unavailable:'语音未完成',busy:'语音队列忙',cancelled:'已取消',interrupted:'监听中断'};
 function clock(){const now=new Date(Date.now()+offset);el('smart-clock').textContent=dateFormat.format(now)+' · 北京时间';el('smart-clock').dateTime=now.toISOString();}
 function period(p){
  const root=document.createElement('div');root.className='smart-period';
  root.innerHTML='<label>开始 <input type="time" class="smart-start" required></label> 至 <label>结束 <input type="time" class="smart-end" required></label> <button type="button" class="btn small smart-remove">删除</button><div class="smart-days"></div>';
  root.querySelector('.smart-start').value=p.start;root.querySelector('.smart-end').value=p.end;
  for(let d=0;d<7;d++){const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.value=d;input.checked=p.days.includes(d);label.append(input,document.createTextNode('周'+'一二三四五六日'[d]));root.querySelector('.smart-days').append(label);}
  root.querySelector('.smart-remove').onclick=()=>{root.remove();periodCount--;};el('smart-periods').append(root);periodCount++;
 }
 function render(s){
  offset=Date.parse(s.server_time)-Date.now();clock();
  if(!loaded){el('smart-enabled').checked=s.config.enabled;for(const p of s.config.periods)period(p);loaded=true;}
  const a=s.advice;el('smart-mode').textContent=a.mode;
  el('smart-parameters').textContent=[a.setpoint_c!=null?`建议温度 ${a.setpoint_c}°C`:a.mode==='送风'?'无需温度设定':'',a.fan?`风速：${a.fan}`:'',a.target_humidity_percent?`目标湿度 ${a.target_humidity_percent}%`:''].filter(Boolean).join(' · ')||'—';
  el('smart-reason').textContent=a.reason;el('smart-updated').textContent=`每 ${a.interval_seconds} 秒更新 · ${dateFormat.format(new Date(a.updated_at))} · 仅提供建议`;
  el('smart-condition').textContent=(s.unauthorized_active?'【非授权时段】':'')+s.condition+(s.error?' · '+s.error:'');
  const list=el('smart-events');list.replaceChildren();
  for(const event of s.events.slice(0,30)){const card=document.createElement('div');card.className='smart-event';const head=document.createElement('strong'),line=document.createElement('p'),detail=document.createElement('p');head.textContent=`${dateFormat.format(new Date(event.received_at))} · 人物 ID ${event.person_id}`;line.textContent=event.phrase;detail.className='sub';detail.textContent=`${voiceNames[event.voice_state]||event.voice_state}：${event.voice_detail}`;card.append(head,line,detail);list.append(card);}
  if(!s.events.length)list.textContent='暂无非授权时段报警';
 }
 async function poll(){if(busy)return;busy=true;try{const r=await fetch('/api/smart-assist',{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);render(await r.json());}catch(_){el('smart-condition').textContent='监测服务连接中断，当前状态不可确认';}finally{busy=false;}}
 el('smart-add').onclick=()=>{if(periodCount>=8){el('smart-save').textContent='最多 8 个时段';return;}period({start:'22:00',end:'06:00',days:[0,1,2,3,4,5,6]});};
 el('smart-form').onsubmit=async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;
  try{const periods=[...document.querySelectorAll('.smart-period')].map(root=>({start:root.querySelector('.smart-start').value,end:root.querySelector('.smart-end').value,days:[...root.querySelectorAll('input[type=checkbox]:checked')].map(i=>Number(i.value))}));
   const r=await fetch('/api/smart-assist/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:el('smart-enabled').checked,periods})});const result=await r.json();if(!r.ok)throw Error(result.error);el('smart-save').textContent='设置已保存，服务器将按北京时间自动监测';await poll();
  }catch(error){el('smart-save').textContent=error.message;}finally{button.disabled=false;}
 };
 clock();setInterval(clock,1000);poll();setInterval(poll,1000);
})();
