"use strict";
const colorVideo={connected:false,retry:0};
function colorStreamEnabled(){return state.image==='latest_camera_preview.png'&&!state.csv;}
function stopColorStream(){
  clearTimeout(colorVideo.retry);colorVideo.retry=0;
  if(colorVideo.connected){$('picture').removeAttribute('src');colorVideo.connected=false;}
}
function ensureColorStream(){
  if(state.paused||!colorStreamEnabled()||colorVideo.connected)return;
  const picture=$('picture');colorVideo.connected=true;
  picture.onload=()=>{picture.hidden=false;$('image-empty').hidden=true;};
  picture.onerror=()=>{colorVideo.connected=false;badge('image-status','视频连接中断，正在重连','amber');
    clearTimeout(colorVideo.retry);colorVideo.retry=setTimeout(ensureColorStream,1500);};
  picture.src='/stream.mjpg?t='+Date.now();
}
function renderColorStream(){
  if(!colorStreamEnabled())return;
  const s=live.snapshot,image=s?.image;
  const fresh=Boolean(!live.error&&image&&s.image_age_ms<3000&&performance.now()-live.checkedAt<3000);
  const color=image?.format==='rgb565',fps=fresh?s.received_image_hz:0;
  $('camera-count').textContent=s?.stream_sequence??'—';
  $('camera-rate').textContent=fps.toFixed(1);
  $('camera-age').textContent=image?(s.image_age_ms/1000).toFixed(1):'—';
  $('camera-frame').textContent=image?.source_count??'—';
  $('camera-received').textContent=image?fmtTime(image.received_at):'—';
  $('camera-csv').textContent='内存视频流 · CSV 每秒存档';
  badge('camera-state',state.paused?'已暂停':fresh?'正在接收'+(color?'彩色视频':'灰度旧版视频'):'视频数据已过期或尚未收到',fresh?'blue':'amber');
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
  $('camera-note').textContent='帧率为最近 10 秒实际收到的完整图像速率，不是 YOLO 检测次数。低功耗时摄像头仍按原设置降至 5 FPS。';
  $('freshness').textContent=state.paused?'视频和自动数据刷新已暂停。':fresh?'正在显示开发板当前彩色视频；YOLO 和跌倒事件独立更新。':'等待板端新图像；旧画面不能作为当前状态。';
  $('freshness').className='update-note'+(fresh?' ok':'');
  if(!state.paused)ensureColorStream();
}
