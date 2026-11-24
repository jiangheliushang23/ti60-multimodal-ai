"""Presentation changes applied to the retained original monitor template."""
import re


def render_page(original):
    html = original.decode('utf8').replace('\r\n', '\n')
    html, count = re.subn(r'  <section class="panel reception".*?</section>\s*', '', html, count=1, flags=re.S)
    if count != 1:
        raise ValueError('Original reception panel changed')
    html = html.replace('<th>同帧图片</th>', '').replace('colspan="8"', 'colspan="7"')
    html, count = re.subn(r'function renderReception\(\)\{.*?\n\}\n(?=async function loadReception)',
                          'function renderReception(){if(colorStreamEnabled())renderColorStream();}\n',
                          html, count=1, flags=re.S)
    if count != 1:
        raise ValueError('Original reception renderer changed')
    html, count = re.subn(r'function renderRows\(\)\{.*?\n\}\n(?=function renderSensors)',
                          'function renderRows(){renderPersonRows();}\n', html, count=1, flags=re.S)
    if count != 1:
        raise ValueError('Original history renderer changed')
    html = html.replace('<script src="color_stream.js"></script>',
                        '<script src="color_stream.js"></script>\n<script src="monitor_view.js"></script>')
    html = html.replace('</head>', '<link rel="stylesheet" href="monitor_view.css">\n</head>')
    html = html.replace('板端真实事件、摄像头记录与页面演示分别标注',
                        '显示板端人体位置、检测分数与真实事件；摄像头记录和页面演示分别标注')
    html = html.replace('TEST 字段是模拟值；CAMERA 帧记录不代表 AI 检测结果。',
                        '位置为 1280×720 画面中的人体中心；纯摄像头帧没有检测分数。')
    return html.encode('utf8')
