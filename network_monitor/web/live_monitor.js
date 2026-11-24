"use strict";
const live = {snapshot:null,checkedAt:0,error:"",busy:false,timer:null,rows:[],selected:null,acknowledged:new Set()};
try { live.acknowledged=new Set(JSON.parse(localStorage.getItem('ti60-viewed-events')||'[]')); } catch (_) {}
const eventNames={fall:'跌倒报警',danger:'危险区预警',power_low:'进入低功耗',power_normal:'恢复正常模式',wake_check:'红外唤醒确认'};
const powerNames=['正常','准备休眠','低功耗','准备唤醒','YOLO 确认'];
function liveOnline(){return Boolean(!state.paused&&!live.error&&live.snapshot?.online&&performance.now()-live.checkedAt<3000);}
function eventRows(){return live.rows;}
function realConfidence(person){return person?.valid&&Number.isFinite(person.score_q15)?(person.score_q15*100/32768).toFixed(1):'';}
function rowStatus(row){return row._board?(live.acknowledged.has(row.event_id)?'页面已阅':'板端事件'):row._demo?(row.acknowledged?'页面已确认':'页面待确认'):'已接收';}
function renderLiveSensors(){
  const demo=state.sensorDemo,t=live.snapshot?.status,online=liveOnline();
  const env=online&&Boolean(t?.environment_valid),ir=online&&Boolean(t?.infrared_valid);
  const tags=document.querySelectorAll('.sensor-tag');
  for(let i=0;i<tags.length;i++){const valid=i===2?ir:env;tags[i].textContent=demo?'页面模拟':valid?'板端实时':online?'无有效数据':live.snapshot?.status?'数据已过期':'等待板端';tags[i].className='pill sensor-tag'+(demo?' amber':valid?' blue':'');}
  $('temperature').textContent=demo?'27.2':env?t.temperature_c.toFixed(2):'—';
  $('humidity').textContent=demo?'52.8':env?t.humidity_percent.toFixed(2):'—';
  $('infrared').textContent=demo?'36.5':ir?t.ir_max_c.toFixed(1):'—';
  $('temp-note').textContent=demo?'固定演示值，不来自 SHT30':env?'SHT30 · 板端环境温度':'等待有效 SHT30 数据';
  $('humidity-note').textContent=demo?'固定演示值，不来自 SHT30':env?'SHT30 · 板端环境湿度':'等待有效 SHT30 数据';
  $('ir-note').textContent=demo?'固定演示值，不代表体温测量':ir?`MLX90640 最高温 · 最低 ${t.ir_min_c.toFixed(1)} / 中心 ${t.ir_center_c.toFixed(1)} °C`:'等待有效 MLX90640 温度';
  $('temp-meter').style.width=demo?'54%':env?Math.max(0,Math.min(100,t.temperature_c*2))+'%':'0';
  $('humidity-meter').style.width=demo?'52.8%':env?Math.max(0,Math.min(100,t.humidity_percent))+'%':'0';
  $('ir-meter').style.width=demo?'73%':ir?Math.max(0,Math.min(100,t.ir_max_c*2))+'%':'0';
  $('demo-sensors').textContent=demo?'关闭传感器演示':'演示传感器';$('demo-sensors').setAttribute('aria-pressed',String(demo));
}
function realEventFor(person,type){return live.rows.find(row=>row.id===person.id&&row.type===type)||null;}
function renderLiveAlarm(){
  const online=liveOnline(),t=live.snapshot?.status;
  const people=online?t.people.filter(p=>p.id):[];
  const person=people.find(p=>p.alarm);
  let title,subtitle,type='—',score='—',note,tag,style='',id='—',positionText='—',time='—',active=false;
  live.selected=null;
  if(person){
    const kind='fall',event=realEventFor(person,kind),viewed=Boolean(event&&live.acknowledged.has(event.event_id));
    live.selected=event;active=kind==='fall';tag=kind==='fall'?'板端实时报警':'板端实时预警';style=kind==='fall'?'red':'amber';
    title=eventNames[kind];subtitle=`人物 ID ${person.id}`+(viewed?' · 页面已阅，板端状态继续显示':' · 来自 FPGA 检测');
    type=eventNames[kind];score=realConfidence(person);score=score?score+'%':'—';id=String(person.id);
    const b=person.box;positionText=`中心 (${Math.round((b[0]+b[2])/2)}, ${Math.round((b[1]+b[3])/2)})`;
    time=event?fmtTime(event.received_at):'等待事件记录';
    note='跌倒由板端几何算法判断；这里的分数是人体检测分数。页面确认不解除硬件报警。';
  }else if(state.alarm){
    const alarm=state.alarm;active=!alarm.acknowledged;tag='页面模拟告警';style='amber';
    title=alarm.acknowledged?'页面告警已确认':'跌倒告警 · 页面演示';subtitle='此告警由网页按钮生成';
    type='跌倒（模拟）';score='92%（模拟）';id=alarm.id;time=fmtTime(alarm.received_at);
    note=alarm.acknowledged?'确认只作用于当前页面，未向开发板回传。':'模拟事件不控制开发板 LED、语音或任何实际硬件。';
  }else{
    const previous=live.rows.find(row=>row.type==='fall');
    if(previous){
      live.selected=previous;const viewed=live.acknowledged.has(previous.event_id);
      tag='历史板端事件';style='amber';title='最近'+eventNames[previous.type]+(viewed?' · 已阅':' · 待阅');
      subtitle=online?'当前无跌倒报警':'当前板端状态不可确认；下方为历史事件';
      type=eventNames[previous.type];score=previous.confidence_pct?previous.confidence_pct+'%':'—';id=String(previous.id);
      positionText=position(previous);time=fmtTime(previous.received_at);note='历史记录不代表当前状态；事件时间显示电脑接收时间。';
    }else{
      tag=online?'板端实时':'等待板端事件';style=online?'blue':'';
      title=online?'当前无跌倒报警':'等待真实事件数据';
      subtitle=state.paused?'网页刷新已暂停':live.error?'电脑事件接口暂不可用':online?`已连接 · ${powerNames[t.power_mode]||'未知模式'}`:'尚无有效板端状态，不能据此判断现场安全';
      note='真实跌倒和电源模式变化会自动进入历史记录。';
    }
  }
  badge('alarm-tag',tag,style);$('alarm-body').classList.toggle('active',active);
  $('alarm-title').textContent=title;$('alarm-subtitle').textContent=subtitle;$('alarm-type').textContent=type;
  $('alarm-confidence').textContent=score;$('alarm-person').textContent=id;$('alarm-position').textContent=positionText;
  $('alarm-time').textContent=time;$('alarm-note').textContent=note;
  $('acknowledge').disabled=live.selected?live.acknowledged.has(live.selected.event_id):!state.alarm||state.alarm.acknowledged;
}
function acknowledgeDisplayed(){
  if(live.selected){
    live.acknowledged.add(live.selected.event_id);
    try{localStorage.setItem('ti60-viewed-events',JSON.stringify([...live.acknowledged].slice(-400)));}catch(_){}
    toast('已在此浏览器标记已阅；板端报警、语音和检测继续运行。');
  }else if(state.alarm){state.alarm.acknowledged=true;toast('已在页面确认模拟告警。');}
  renderAlarm();renderRows();
}
function renderLiveConnection(){
  const s=live.snapshot,t=s?.status,online=liveOnline();
  $('live-connection').textContent=state.paused?'已暂停刷新':live.error?'接口连接中断':online?'在线 · 板端实时':t?'板端状态已过期':'等待板端';
  $('live-mode').textContent=online?`${powerNames[t.power_mode]||'未知'} · ${t.detection_hz.toFixed(1)} 次/秒 · ${t.inference_ms} ms`:'—';
  $('live-people').textContent=online?t.people.filter(p=>p.valid).map(p=>`ID ${p.id}：${p.alarm?'跌倒报警':'正常'}`).join('；')||'当前无人':'—';
  const n=s?.network;
  $('live-note').textContent=live.error?'网页事件接口读取失败，保留历史记录；重连后自动恢复。':n?.error?'UDP 接收异常：'+n.error:n&&!n.pc_ip_configured?'电脑有线网卡尚无 192.168.0.3；请先完成直连 IP 配置。':online?`事件接口每 0.5 秒读取；最近板端状态距今 ${s.status_age_ms} ms。`:'等待有效板端 UDP 状态；历史事件与当前在线状态分别显示。';
}
async function pollLive(force=false){
  if(live.busy||state.paused&&!force)return;
  live.busy=true;const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),1500);
  try{
    const response=await fetch('/api/status',{cache:'no-store',signal:controller.signal});
    if(!response.ok)throw Error(`HTTP ${response.status}`);
    const snapshot=await response.json();
    if(!Array.isArray(snapshot.events))throw Error('Invalid event interface');
    live.snapshot=snapshot;live.error='';live.checkedAt=performance.now();
    live.rows=snapshot.events.map(event=>{
      const p=event.person,b=p?.box;
      return {_board:true,event_id:event.event_id,received_at:event.received_at,kind:'BOARD_EVENT',type:event.type,
        id:p?.id??'',confidence_pct:realConfidence(p),source_ip:'192.168.0.2',source_port:8080,
        x:b?Math.round((b[0]+b[2])/2):undefined,y:b?Math.round((b[1]+b[3])/2):undefined,
        device_ms:event.device_ms,capture_ms:event.capture_ms,thumbnail:event.thumbnail||null};
    });
  }catch(error){live.error=error.name==='AbortError'?'读取超时':error.message;}
  finally{
    clearTimeout(timer);live.busy=false;
    renderSensors();renderAlarm();renderLiveConnection();renderRows();if(colorStreamEnabled())renderColorStream();
  }
}
function startLiveMonitor(){
  pollLive();live.timer=setInterval(()=>pollLive(),500);
  $('refresh').addEventListener('click',()=>pollLive(true));
  $('pause').addEventListener('click',()=>{renderSensors();renderAlarm();renderLiveConnection();if(state.paused)stopColorStream();else{ensureColorStream();pollLive();}});
}
