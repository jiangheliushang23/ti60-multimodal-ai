"""Add comfort/schedule controls without rewriting the retained original page."""
SECTION = '''
<section class="panel smart-panel" id="smart-assist" aria-labelledby="smart-title">
 <div class="panel-head"><h2 id="smart-title">环境建议与非授权时段监测</h2>
 <time id="smart-clock" aria-label="当前具体时间">正在同步电脑时间</time></div>
 <div class="smart-grid"><div><h3>空调控制建议</h3>
 <p class="smart-mode" id="smart-mode">等待环境数据</p>
 <p id="smart-parameters">—</p><p class="sub" id="smart-reason"></p>
 <p class="sub" id="smart-updated">每 3 秒更新；仅提供建议，不实际控制空调。</p></div>
 <div><h3>非授权时段设置</h3><form id="smart-form">
 <label><input type="checkbox" id="smart-enabled">启用非授权时段语音报警</label>
 <div id="smart-periods"></div><div class="actions">
 <button type="button" class="btn small" id="smart-add">添加时段</button>
 <button type="submit" class="btn small">保存设置</button></div>
 <p class="sub" id="smart-save" role="status"></p></form>
 <p id="smart-condition" role="status">等待板端数据</p>
 <p class="sub">时区固定为北京时间。跨午夜时段的星期按开始日期计算。设置保存在电脑服务器，关闭浏览器不影响监测。</p>
 <p class="sub">启用报警且处于非授权时段时，有效人物框出现即触发语音；绿框、跌倒红框及像素续跟框均计入，无需红外温度、额外分数或持续 1 秒确认。同一人物最多每 60 秒播报一次，跌倒语音优先。</p>
 </div></div><h3>非授权时段报警记录</h3><div id="smart-events" class="smart-events">暂无报警</div>
</section><script src="smart_assist.js" defer></script>
'''


def enhance(html):
    clock = '<time id="smart-clock" aria-label="当前具体时间">正在同步电脑时间</time>'
    panel = SECTION.replace(clock, '')
    return html.replace(b'</head>', b'<link rel="stylesheet" href="smart_assist.css"></head>', 1).replace(
        b'</header>', clock.encode('utf8') + b'</header>', 1).replace(
        b'<section class="panel history"', panel.encode('utf8') + b'<section class="panel history"', 1)
