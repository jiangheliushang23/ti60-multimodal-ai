"use strict";
(() => {
  const el = id => document.getElementById(id);
  // getRandomValues also works on ordinary LAN HTTP; randomUUID requires HTTPS.
  const viewer = Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2,'0')).join('');
  let selected = '', meta = null, index = 0, playing = false, requestVersion = 0, listBusy = false;
  const route = () => '/fall-clips/' + encodeURIComponent(selected);
  const offset = i => meta ? meta.frames[i].ms - meta.frames[0].ms : 0;
  const label = clip => {
    const person = clip.event.person?.id ?? '—';
    const time = new Date(clip.event.received_at).toLocaleString();
    return `${time} · ID ${person} · ${clip.state === 'recording' ? '正在收集后5秒' : clip.complete ? '完整10秒' : '片段不完整'}`;
  };
  async function get(path) {
    const response = await fetch(path, {cache:'no-store', signal:AbortSignal.timeout(5000)});
    if (!response.ok) throw Error(response.status === 404 ? '录像已被容量清理，请刷新列表' : '录像读取失败（'+response.status+'）');
    return response.json();
  }
  function renderPosition() {
    if (!meta?.frames.length) return;
    const relative = (meta.frames[index].ms - meta.event_ms) / 1000;
    el('fall-timeline').value = offset(index);
    el('fall-position').textContent = `第 ${index+1}/${meta.frames.length} 帧 · 跌倒${relative<0?'前':'后'} ${Math.abs(relative).toFixed(2)} 秒`;
  }
  function still() {
    if (!meta?.frames.length) return;
    el('fall-picture').src = `${route()}/frame/${index}.jpg`;
    el('fall-picture').hidden = false; el('fall-empty').hidden = true;
    renderPosition();
  }
  async function pause(show = true) {
    playing = false; el('fall-play').textContent = '播放';
    el('fall-picture').removeAttribute('src');
    try { await get('/api/fall-playback?viewer='+viewer+'&stop=1'); } catch (_) {}
    if (show) still();
  }
  function start() {
    if (!meta?.frames.length) return;
    if (index === meta.frames.length-1) index = 0;
    playing = true; el('fall-play').textContent = '暂停';
    el('fall-picture').hidden = false; el('fall-empty').hidden = true;
    el('fall-picture').src = `${route()}/stream.mjpg?viewer=${viewer}&offset_ms=${offset(index)}&speed=${el('fall-speed').value}`;
  }
  async function load(identifier) {
    const version = ++requestVersion;
    await pause(false); selected = identifier; meta = null; index = 0;
    for (const name of ['fall-play','fall-previous','fall-next','fall-jump','fall-timeline']) el(name).disabled = true;
    el('fall-download').hidden = true; el('fall-event-mark').style.display = 'none';
    if (!identifier) {el('fall-picture').hidden=true;el('fall-empty').hidden=false;el('fall-detail').textContent='';el('fall-position').textContent='—';return;}
    try {
      const value = await get('/api/fall-clips/'+encodeURIComponent(identifier));
      if (version !== requestVersion) return;
      meta = value;
      if (!meta.frames.length) throw Error('未收到可保存画面；请检查视频连接');
      for (const name of ['fall-play','fall-previous','fall-next','fall-jump','fall-timeline']) el(name).disabled = false;
      el('fall-timeline').max = meta.duration_ms;
      const warnings = [];
      if (!meta.pre_complete) warnings.push('前5秒不足');
      if (!meta.post_complete) warnings.push('后5秒不足');
      if (meta.gaps_over_500ms) warnings.push('中间存在视频中断');
      if (meta.dropped_frames) warnings.push('部分帧未保存');
      const delta = meta.event_frame_delta_ms;
      el('fall-detail').textContent = `${meta.width||'—'} × ${meta.height||'—'} · ${meta.fps} FPS · ${meta.frames.length} 个真实源帧` +
        ` · ${warnings.length ? warnings.join('，') : '前后5秒完整'}` +
        ` · 跌倒时刻画面与检测时间相差 ${delta} ms`;
      el('fall-event-mark').style.display = 'block';
      el('fall-event-mark').style.left = Math.max(0,Math.min(100,(meta.event_ms-meta.frames[0].ms)/Math.max(1,meta.duration_ms)*100))+'%';
      el('fall-download').href = route()+'/download.zip'; el('fall-download').hidden = false;
      still();
    } catch (error) {
      if (version !== requestVersion) return;
      el('fall-detail').textContent = error.message;
      el('fall-picture').hidden = true; el('fall-empty').hidden = false;
    }
  }
  async function refresh() {
    if (listBusy) return; listBusy = true;
    try {
      const data = await get('/api/fall-clips');
      el('fall-storage').textContent = `${(data.storage_bytes/1048576).toFixed(1)} / 512 MiB`;
      el('fall-list-state').textContent = `${data.clips.length} 段跌倒录像` + (data.pending?` · ${data.pending} 段正在收集后5秒`:'') +
        (data.error?' · 录像异常：'+data.error:'') + (data.dropped_frames?' · 写入队列曾丢帧':'');
      const select = el('fall-clips'), available = data.clips.filter(c=>c.state!=='recording');
      const previous = selected;
      select.replaceChildren();
      if (!available.length) {const option = new Option(data.pending?'正在收集跌倒后的画面…':'暂无跌倒录像','');select.add(option);}
      for (const clip of available) select.add(new Option(label(clip),clip.id));
      const next = available.some(c=>c.id===previous)?previous:available[0]?.id||'';
      select.value = next;
      if (next !== selected) await load(next);
    } catch (error) { el('fall-list-state').textContent = error.message; }
    finally { listBusy = false; }
  }
  el('fall-clips').addEventListener('change',()=>load(el('fall-clips').value));
  el('fall-refresh').addEventListener('click',refresh);
  el('fall-play').addEventListener('click',()=>playing?pause():start());
  async function move(next) {await pause(false);index=next;still();}
  el('fall-previous').addEventListener('click',()=>move(Math.max(0,index-1)));
  el('fall-next').addEventListener('click',()=>move(Math.min(meta.frames.length-1,index+1)));
  el('fall-jump').addEventListener('click',()=>move(meta.event_frame_index));
  el('fall-timeline').addEventListener('input',()=>{if(!meta)return;const target=Number(el('fall-timeline').value);let next=0;while(next+1<meta.frames.length&&offset(next+1)<=target)next++;move(next);});
  el('fall-speed').addEventListener('change',async()=>{const wasPlaying=playing;await pause(false);if(wasPlaying)start();else still();});
  el('fall-picture').addEventListener('error',()=>{if(playing){playing=false;el('fall-play').textContent='播放';}el('fall-detail').textContent='回放图像暂不可用，请刷新录像列表。';});
  setInterval(async()=>{if(!playing)return;try{const status=await get('/api/fall-playback?viewer='+viewer);if(status.clip!==selected)return;index=status.index??index;renderPosition();if(!status.running){playing=false;el('fall-play').textContent='播放';still();}}catch(_){playing=false;el('fall-play').textContent='播放';}},250);
  refresh(); setInterval(refresh,2000);
})();
