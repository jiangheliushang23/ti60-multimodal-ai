"""PC-side three-second comfort advice and scheduled visible-person alarms."""
from collections import deque
from datetime import datetime, timedelta, timezone
import copy
import json
import math
import os
from pathlib import Path
import queue
import re
import threading
import time
import uuid

TZ = timezone(timedelta(hours=8), 'Asia/Shanghai')
PHRASE = '非授权时段人人体出现，请及时关注'
ADVICE_INTERVAL_SECONDS = 3
ALARM_COOLDOWN_SECONDS = 60
DEFAULT = dict(version=1, enabled=False, timezone='Asia/Shanghai',
               periods=[dict(start='22:00', end='06:00', days=list(range(7)))])


def validate_config(value):
    if not isinstance(value, dict) or not isinstance(value.get('enabled'), bool):
        raise ValueError('请设置报警开关')
    periods = value.get('periods')
    if not isinstance(periods, list) or not 1 <= len(periods) <= 8:
        raise ValueError('请设置 1 至 8 个时段')
    cleaned = []
    for period in periods:
        if not isinstance(period, dict):
            raise ValueError('时段格式错误')
        start, end, days = period.get('start'), period.get('end'), period.get('days')
        if not all(isinstance(v, str) and re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', v) for v in (start, end)) or start == end:
            raise ValueError('起止时间须为 HH:MM，且不能相同；跨午夜时段受支持')
        if not isinstance(days, list) or not days or any(type(d) is not int or not 0 <= d <= 6 for d in days):
            raise ValueError('请至少选择一个星期，星期一为 0')
        cleaned.append(dict(start=start, end=end, days=sorted(set(days))))
    return dict(version=1, enabled=value['enabled'], timezone='Asia/Shanghai', periods=cleaned)


def in_period(config, now):
    if not config['enabled']:
        return False
    minute = now.hour * 60 + now.minute
    for p in config['periods']:
        start, end = [int(v[:2]) * 60 + int(v[3:]) for v in (p['start'], p['end'])]
        day = now.weekday()
        if start < end and day in p['days'] and start <= minute < end:
            return True
        if start > end and ((day in p['days'] and minute >= start) or ((day - 1) % 7 in p['days'] and minute < end)):
            return True
    return False


def people_present(status):
    age = (status['device_ms'] - status['capture_ms']) & 0xffffffff
    return [p for p in status['people'] if p['id'] and p['valid']] if age <= 1500 and status['power_mode'] != 2 else []


def comfort(status, online, now):
    result = dict(updated_at=now.isoformat(), interval_seconds=ADVICE_INTERVAL_SECONDS, mode='等待数据', setpoint_c=None,
                  fan=None, reason='等待开发板及有效环境温湿度', people=0, controls_hardware=False)
    if not online or not status:
        return result
    people = people_present(status)
    result['people'] = len(people)
    if not people:
        result.update(mode='节能待机', reason='当前未检出人体，建议关闭空调或保持节能待机')
        return result
    t, h = status['temperature_c'], status['humidity_percent']
    if not status['environment_valid'] or abs(status['env_delta_ms']) > 1500 or not (math.isfinite(t) and math.isfinite(h) and -20 <= t <= 60 and 0 <= h <= 100):
        result['reason'] = '已检出人体，但环境温湿度无效或过期，暂不提供调控参数'
        return result
    result.update(temperature_c=t, humidity_percent=h)
    if t >= 28:
        result.update(mode='制冷', setpoint_c=26, fan='高风' if t >= 32 else '中风', reason='环境偏热；有人员在场，建议设定 26°C，避免冷风直吹')
    elif t < 20:
        result.update(mode='制热', setpoint_c=22, fan='中风' if t < 16 else '低风', reason='环境偏冷；建议设定 22°C，避免短时间大幅升温')
    elif h >= 65:
        result.update(mode='除湿', setpoint_c=26 if t >= 26 else 24, fan='低风', target_humidity_percent=55,
                      reason='湿度偏高，目标相对湿度约 55%；冷房时避免过度降温')
    else:
        result.update(mode='送风', fan='中风' if t >= 26 else '低风', reason='温湿度较舒适，建议送风；送风模式无需设置制冷温度')
    if h < 35:
        result['reason'] += '；湿度偏低，建议适当加湿'
    return result


class VoiceGateway:
    """Acquire existing USB UART only for one verified request; never reset CPU."""
    def __init__(self, callback, allowed, port=None):
        self.callback, self.allowed, self.port = callback, allowed, port or os.environ.get('TI60_VOICE_PORT')
        self.pending = queue.Queue(maxsize=4)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, name='scheduled-voice', daemon=True)
        self.thread.start()

    def offer(self, event):
        try:
            self.pending.put_nowait(event)
        except queue.Full:
            self.callback(event['event_id'], 'busy', '语音请求队列已满')

    def run(self):
        while not self.stop.is_set():
            try:
                event = self.pending.get(timeout=.2)
            except queue.Empty:
                continue
            if not self.allowed(event):
                self.callback(event['event_id'], 'cancelled', '现场状态或时段已变化，取消过期语音')
                continue
            try:
                self.transmit(event)
            except Exception as error:
                self.callback(event['event_id'], 'unavailable', str(error))

    def transmit(self, event):
        import serial
        from serial.tools import list_ports
        # The board has multiple FT4232 channels. Select UART channel C exactly,
        # using the same registry identity as the production downloader.
        ports = {p.device for p in list_ports.comports() if (p.vid, p.pid) == (0x403, 0x6011)}
        matches = []
        if not self.port:
            import winreg
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Enum\FTDIBUS') as bus:
                    for i in range(winreg.QueryInfoKey(bus)[0]):
                        name = winreg.EnumKey(bus, i)
                        if name.startswith('VID_0403+PID_6011+') and name.endswith('&3'):
                            try:
                                with winreg.OpenKey(bus, name + r'\0000\Device Parameters') as key:
                                    found = winreg.QueryValueEx(key, 'PortName')[0]
                                if found in ports:
                                    matches.append(found)
                            except FileNotFoundError:
                                pass
            except FileNotFoundError:
                pass
        port = self.port or (matches[0] if len(set(matches)) == 1 else None)
        if not port:
            raise RuntimeError('未找到唯一的开发板串口；请接好 USB 串口并关闭串口助手/下载会话')
        connection = serial.Serial(port=None, baudrate=500000, timeout=.1, write_timeout=1)
        connection.dtr = False
        connection.rts = False
        connection.port = port
        with connection:
            connection.reset_input_buffer()
            connection.write(b'J')
            buffer = b''
            deadline = time.monotonic() + 4
            ready, sent, accepted = False, False, False
            completed_before = None
            while not self.stop.is_set() and time.monotonic() < deadline:
                buffer += connection.read(min(4096, max(1, connection.in_waiting)))
                if len(buffer) > 65536:
                    buffer = buffer[-32768:]
                while b'\n' in buffer:
                    raw, buffer = buffer.split(b'\n', 1)
                    line = raw.decode('ascii', errors='replace').strip()
                    if not sent and line.startswith('SMART_CAPS version=1 '):
                        ready = True
                        if not self.allowed(event):
                            raise RuntimeError('现场状态或时段已变化，未发送语音')
                        connection.write(b'U')
                        sent = True
                        deadline = time.monotonic() + 38
                    elif sent and line.startswith('ASSIST_VOICE '):
                        if 'queued=1' not in line:
                            raise RuntimeError('语音模块未就绪或正忙，未接收请求')
                        self.callback(event['event_id'], 'queued', '开发板已接受语音请求，跌倒播报优先')
                    elif sent and line.startswith('VOICE_STATE ') and 'source=UNAUTHORIZED ' in line:
                        fields = dict(re.findall(r'(\w+)=(\S+)', line))
                        if completed_before is None:
                            completed_before = int(fields.get('uart_completed', '0'))
                        if fields.get('error') != '0':
                            raise RuntimeError('语音模块未确认完成：' + fields.get('error', 'unknown'))
                        accepted |= fields.get('phase') == '2'
                        if accepted and fields.get('phase') == '0' and fields.get('last_rx') == '4f':
                            # Two UART parts: completion is counted only after the second.
                            if int(fields.get('uart_completed', '0')) > completed_before:
                                self.callback(event['event_id'], 'module_completed', '语音模块确认播放完成；实际声音请现场确认')
                                return
            if self.stop.is_set():
                self.callback(event['event_id'], 'interrupted', '服务关闭，中止串口监听')
                return
            raise RuntimeError('需要下载 v22 配套固件' if not ready else '语音完成确认超时，未宣称播报成功')

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)


class SmartAssist:
    def __init__(self, records, gateway_factory=VoiceGateway, start_worker=True):
        self.records = Path(records)
        self.path = self.records / 'smart_assist_config.json'
        self.lock = threading.RLock()
        self.config = copy.deepcopy(DEFAULT)
        self.error = None
        if self.path.exists():
            try:
                self.config = validate_config(json.loads(self.path.read_text(encoding='utf8')))
            except (ValueError, OSError) as error:
                self.error = '时段配置读取失败，报警保持关闭：' + str(error)
        self.events = deque(maxlen=100)
        self.event_path = self.records / 'access_events.jsonl'
        if self.event_path.exists():
            restored = {}
            for line in self.event_path.read_text(encoding='utf8').splitlines()[-400:]:
                try:
                    value = json.loads(line)
                    restored[value['event_id']] = value
                except ValueError:
                    pass
            self.events.extend(reversed(list(restored.values())[-100:]))
        self.status = None
        self.received = 0
        self.cooldown = {}
        self.last_device = None
        self.advice_at = -100
        self.advice = comfort(None, False, datetime.now(TZ))
        self.active = False
        self.eligible = []
        self.reason = '等待开发板数据'
        self.stop = threading.Event()
        self.gateway = gateway_factory(self.voice_update, self.allowed)
        self.thread = threading.Thread(target=self.run, name='smart-assist', daemon=True)
        if start_worker:
            self.thread.start()

    def configure(self, value):
        cleaned = validate_config(value)
        with self.lock:
            temp = self.path.with_suffix('.tmp')
            temp.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding='utf8')
            temp.replace(self.path)
            self.config = cleaned
            self.cooldown.clear()
            self.error = None
        return copy.deepcopy(cleaned)

    def observe(self, status, now=None):
        with self.lock:
            if self.last_device is not None and (status['device_ms'] - self.last_device) & 0xffffffff >= 0x80000000:
                self.cooldown.clear()
            self.last_device = status['device_ms']
            self.status = copy.deepcopy(status)
            self.received = time.monotonic() if now is None else now

    def allowed(self, event):
        with self.lock:
            current = self.status or {}
            # Use the same valid detections that feed the HDMI rectangles.
            # Pixel-supported boxes and either red or green boxes qualify.
            confirmed = any(p['id'] == event['person_id'] for p in people_present(current)) if current else False
            return (not self.stop.is_set() and self.active and in_period(self.config, datetime.now(TZ))
                    and time.monotonic() - self.received < 3 and event['person_id'] in self.eligible
                    and confirmed and time.monotonic() - event['_created'] < 8)

    def voice_update(self, identifier, value, detail):
        with self.lock:
            for event in self.events:
                if event['event_id'] == identifier:
                    event.update(voice_state=value, voice_detail=detail)
                    with self.event_path.open('a', encoding='utf8') as output:
                        output.write(json.dumps({k: v for k, v in event.items() if not k.startswith('_')}, ensure_ascii=False) + '\n')
                    break

    def tick(self, mono=None, wall=None):
        mono = time.monotonic() if mono is None else mono
        wall = datetime.now(TZ) if wall is None else wall
        offers = []
        with self.lock:
            online = self.status is not None and mono - self.received < 3
            if mono - self.advice_at >= ADVICE_INTERVAL_SECONDS:
                self.advice = comfort(self.status, online, wall)
                self.advice_at = mono
            self.active = in_period(self.config, wall)
            status = self.status or {}
            people = people_present(status) if online else []
            ids = list(dict.fromkeys(p['id'] for p in people)) if self.active else []
            self.eligible = ids
            self.reason = ('报警未启用' if not self.config['enabled'] else '当前不在非授权时段' if not self.active
                           else '等待实时开发板数据' if not online
                           else '等待显示有效人物框' if not people
                           else '已显示有效人物框，触发非授权时段报警；同一人物每 60 秒最多播报一次')
            for identity in ids:
                if mono - self.cooldown.get(identity, -1000) < ALARM_COOLDOWN_SECONDS:
                    continue
                person = next(p for p in people if p['id'] == identity)
                self.cooldown[identity] = mono
                event = dict(event_id=uuid.uuid4().hex, type='unauthorized_person', received_at=wall.isoformat(),
                             person_id=identity, score_q15=person['score_q15'], box=person['box'],
                             trigger='visible_person_box',
                             phrase=PHRASE, voice_state='pending', voice_detail='等待语音模块', _created=mono)
                self.events.appendleft(event)
                with self.event_path.open('a', encoding='utf8') as output:
                    output.write(json.dumps({k: v for k, v in event.items() if not k.startswith('_')}, ensure_ascii=False) + '\n')
                offers.append(event.copy())
        for event in offers:
            self.gateway.offer(event)

    def run(self):
        while not self.stop.wait(.25):
            try:
                self.tick()
            except Exception as error:
                with self.lock:
                    self.error = str(error)

    def snapshot(self):
        with self.lock:
            return dict(server_time=datetime.now(TZ).isoformat(), timezone='Asia/Shanghai', config=copy.deepcopy(self.config),
                        advice=copy.deepcopy(self.advice), unauthorized_active=self.active, qualifying_ids=self.eligible[:],
                        condition=self.reason, error=self.error,
                        alarm_trigger='visible_person_box', confirmation_seconds=0,
                        cooldown_seconds=ALARM_COOLDOWN_SECONDS, thermal_required=False,
                        events=[{k: v for k, v in e.items() if not k.startswith('_')} for e in self.events])

    def close(self):
        self.stop.set()
        if self.thread.is_alive():
            self.thread.join(timeout=2)
        self.gateway.close()
