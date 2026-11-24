"use strict";
// Keep the original live stream/controls; the removed diagnostic panel has no DOM placeholders.
renderColorStream = function() {
  if(!colorStreamEnabled())return;
  const s=live.snapshot,image=s?.image;
  const fresh=Boolean(!live.error&&image&&s.image_age_ms<3000&&performance.now()-live.checkedAt<3000);
  const color=image?.format==='rgb565',fps=fresh?s.received_image_hz:0;
  badge('image-kind',color?'摄像头真实彩色':'等待彩色固件',color?'blue':'amber');
  badge('image-status',state.paused?'视频已暂停':fresh?'实时视频流':'等待新画面',fresh?'blue':'amber');
  $('resolution').textContent=image?`${image.width} × ${image.height} · ${color?'RGB565 彩色':'灰度'} · ${fps.toFixed(1)} FPS`:'等待真实摄像头帧';
  $('video-label').textContent=state.paused?'已暂停':fresh?(color?'COLOR / 实时摄像头':'GRAY / 旧固件'):'画面已过期';
  $('picture').alt='开发板摄像头实时'+(color?'彩色':'灰度')+'画面';
  if(image){$('picture').hidden=false;$('image-empty').hidden=true;}
  $('last-received').textContent=image?fmtTime(image.received_at):'—';
  $('data-time').textContent=image?fmtTime(image.received_at):'—';
  $('source-ip').textContent=image?'192.168.0.2:8080':'—';
  $('data-source').textContent='开发板摄像头 · UDP → 连续 MJPEG';
  $('freshness').textContent=state.paused?'视频和自动数据刷新已暂停。':fresh?'正在显示开发板当前彩色视频；YOLO 和跌倒事件独立更新。':'等待板端新图像；旧画面不能作为当前状态。';
  $('freshness').className='update-note'+(fresh?' ok':'');
  if(!state.paused)ensureColorStream();
};

eventNames.person='人体检测';eventNames.no_person='未检出人体';
eventRows = function(){return [...live.rows,...(live.snapshot?.person_records||[])];};
const originalRowStatus=rowStatus;
rowStatus = function(row){
  if(row._detection)return row._missing?'未检出人体':row._pixels?'像素跟踪':row._alarm?'跌倒报警':'正常';
  return originalRowStatus(row);
};

function renderPersonRows(){
  const rows=rowsFiltered(),body=$('records');body.replaceChildren();
  for(const row of rows.slice(0,100)){
    const tr=body.insertRow(),timeCell=tr.insertCell();timeCell.textContent=fmtTime(row.received_at);
    tr.dataset.recordType=row._detection?'person':category(row);if(row.id)tr.dataset.personId=String(row.id);
    if(row._board)timeCell.title=`板端检测图像 ${row.capture_ms} ms，状态 ${row.device_ms} ms`;
    const cell=tr.insertCell(),span=document.createElement('span'),kind=category(row);
    span.className='pill '+(kind==='demo'||kind==='test'?'amber':kind==='camera'||kind==='board'?'blue':'');
    span.textContent=row._detection?'板端人体检测':labelCategory(kind);cell.append(span);
    const score=confidence(row)+(row._pixels&&confidence(row)!=='—'?'（跟踪）':'');
    const center=Number.isFinite(row.x)&&Number.isFinite(row.y)?`(${row.x}, ${row.y})`:'—';
    for(const text of [eventName(row),row.id||row.display_frame_id||'—',center,score,rowStatus(row)])tr.insertCell().textContent=text;
  }
  if(!rows.length){const cell=body.insertRow().insertCell();cell.colSpan=7;cell.className='table-empty';cell.textContent='当前筛选下没有记录';}
  $('table-count').textContent=`共 ${rows.length} 条，显示最近 ${Math.min(rows.length,100)} 条`;
  $('export').disabled=!rows.length;$('clear-demo').disabled=!state.demos.length;
  const count=state.rows.length+eventRows().length;$('record-count').textContent=count;$('record-meter').style.width=count?'100%':'0';
}

function addVideoZoom(stage,label){
  if(!stage)return;
  const button=document.createElement('button');button.type='button';button.className='video-zoom';button.textContent='全屏';button.setAttribute('aria-label',label+'全屏显示');
  button.addEventListener('click',async()=>{
    try{if(document.fullscreenElement)await document.exitFullscreen();else if(stage.requestFullscreen)await stage.requestFullscreen();else toast('当前浏览器不支持全屏，请使用横屏观看');}
    catch(_){toast('无法进入全屏，请使用浏览器的全屏功能');}
  });
  document.addEventListener('fullscreenchange',()=>{button.textContent=document.fullscreenElement===stage?'退出全屏':'全屏';});
  stage.append(button);
}
document.addEventListener('DOMContentLoaded',()=>{
  addVideoZoom($('picture')?.closest('.video-stage'),'实时画面');
  addVideoZoom($('fall-picture')?.closest('.video-stage'),'回放画面');
});
