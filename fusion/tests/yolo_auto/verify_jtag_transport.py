"""Exercise transfer integrity and bounded USB failures without hardware."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SW = ROOT/'fusion/demo_multimodal/software/standalone/tinyml_yolo_static'
sys.path.insert(0, str(SW))
from yolo_auto_jtag import JtagTransport,readback_diagnostic
from yolo_auto_download import camera_frames_advance


class TransportTests(unittest.TestCase):
    def test_camera_sequence_after_sleep_monitor_leases(self):
        a=dict(seq=10,source_count=100,skipped=0,uptime_ms=1000)
        b=dict(seq=11,source_count=115,skipped=14,uptime_ms=1500)
        c=dict(seq=13,source_count=150,skipped=2,uptime_ms=8000)
        self.assertTrue(camera_frames_advance([a,b,c]))
        self.assertFalse(camera_frames_advance([a,dict(b,skipped=13)]))
        self.assertFalse(camera_frames_advance([b,dict(c,source_count=115)]))
        self.assertFalse(camera_frames_advance([a,dict(b,seq=10)]))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.cfg = self.path/'template.cfg'
        self.cfg.write_text('adapter speed 1000\ntransport select jtag\n')
        self.transport = JtagTransport('unused.exe', self.cfg, self.path, notify=lambda _: None)
        self.calls = []

    def tearDown(self):
        self.temp.cleanup()

    def simulated(self, faults=None):
        def run(label, commands, khz=None, timeout=40):
            self.calls.append((label, commands, khz))
            if not any(c.startswith('load_image ') for c in commands):
                return ''
            load = next(c for c in commands if c.startswith('load_image ')).split()
            dump = next(c for c in commands if c.startswith('dump_image ')).split()
            self.assertEqual(load[2], dump[2])
            data = (self.path/load[1]).read_bytes()
            self.assertEqual(len(data), int(dump[3]))
            actual = faults(label, data) if faults else data
            if actual is not None:
                (self.path/dump[1]).write_bytes(actual)
            return 'downloaded %d bytes in 0.5s\ndumped %d bytes in 1.0s\n' % (len(data), len(data))
        return run

    def test_all_bytes_and_tail_without_reset_after_preflight(self):
        data = bytes(range(256))*512+b'Z'
        self.transport.run = self.simulated()
        self.transport.preflight(data)
        result = self.transport.download(data)
        self.assertTrue(result['firmware_readback_exact'])
        self.assertEqual(result['chunk_count'], 3)
        self.assertEqual((self.path/'readback.bin').read_bytes(), data)
        commands = [c for _, cs, _ in self.calls for c in cs]
        self.assertEqual(commands.count('reset halt'), 1)
        self.assertFalse(any(c.startswith('resume') for c in commands))
        self.assertEqual(self.transport.attempts[-1]['bytes'], 1)

    def test_preflight_overwrites_old_firmware_with_changing_signature(self):
        self.transport.run=self.simulated()
        firmware=b'Q'*256
        self.transport.preflight(firmware)
        signature=(self.path/'probe_pattern.bin').read_bytes()
        self.assertEqual(len(set(signature)),256)
        self.assertNotEqual(signature,firmware)
        self.assertEqual([label for label,_,_ in self.calls],['cpu_reset','probe_pattern_try1','probe_try1'])
        self.assertEqual((self.path/'probe_try1_readback.bin').read_bytes(),firmware)
        self.assertEqual(self.calls[0][2],1000)

    def test_real_16_byte_boundary_failure_is_diagnosed(self):
        failed=ROOT/'上板测试记录/YOLO_AUTO_同屏测试_20261027_193402_075241'
        a=(failed/'probe.bin').read_bytes()
        for index in (1,2,3):
            b=(failed/('probe_try%d_readback.bin'%index)).read_bytes()
            proof=readback_diagnostic(a,b)
            self.assertEqual(proof['kind'],'stale_first_word_per_128bit_beat')
            self.assertEqual(proof['mismatch_bytes'],48)
        self.assertEqual(readback_diagnostic(a,a[:-1])['kind'],'length_mismatch')
        self.assertEqual(readback_diagnostic(a,None)['kind'],'missing_readback')
        self.assertEqual(readback_diagnostic(a,b'X'+a[1:])['kind'],'data_mismatch')

    def test_ide_download_uses_stable_one_mhz_explicitly(self):
        import xml.etree.ElementTree as ET
        attrs={e.get('key'):e.get('value') for e in ET.parse(SW/'BEST_TEST_YOLO_AUTO_DOWNLOAD.launch').getroot()}
        self.assertIn('--jtag-khz 1000',attrs['org.eclipse.ui.externaltools.ATTR_TOOL_ARGUMENTS'])

    def test_corruption_retries_only_that_block_and_reduces_clock(self):
        data = b'A'*65536+b'B'*65536
        def fault(label, block):
            return b'X'+block[1:] if label=='block_001_try1' else block
        self.transport.run = self.simulated(fault)
        result = self.transport.download(data)
        self.assertEqual(result['transfer_retries'], 1)
        self.assertEqual(result['jtag_final_khz'], 2000)
        self.assertEqual([a['label'] for a in self.transport.attempts], ['block_000','block_001','block_001'])
        self.assertEqual((self.path/'readback.bin').read_bytes(), data)

    def test_three_bad_readbacks_never_report_success(self):
        self.transport.run = self.simulated(lambda _, block: b'X'+block[1:])
        with self.assertRaisesRegex(RuntimeError, '连续三次'):
            self.transport.download(b'A'*4096)
        self.assertEqual([a['khz'] for a in self.transport.attempts], [4000,2000,1000])
        self.assertEqual((self.path/'readback.bin').stat().st_size, 0)

    def test_truncated_block_does_not_contaminate_verified_prefix(self):
        self.transport.run = self.simulated(lambda label, block: block[:-1] if 'block_001' in label else block)
        with self.assertRaises(RuntimeError):
            self.transport.download(b'A'*65536+b'B'*65536)
        self.assertEqual((self.path/'readback.bin').read_bytes(), b'A'*65536)

    def test_stale_readback_cannot_pass(self):
        for i in range(1,4):
            (self.path/('block_000_try%d_readback.bin' % i)).write_bytes(b'A'*256)
        self.transport.run = self.simulated(lambda _, block: None)
        with self.assertRaises(RuntimeError):
            self.transport.download(b'A'*256)

    def fake_process(self, warning):
        state = {'killed':False}
        class Process:
            def __init__(self, *args, **kwargs):
                kwargs['stdout'].write(warning)
                kwargs['stdout'].flush()
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def wait(self, timeout=None):
                if state['killed']: return -9
                raise subprocess.TimeoutExpired('fake', timeout)
            def poll(self): return -9 if state['killed'] else None
            def kill(self): state['killed']=True
        return Process, state

    def test_usb_stall_is_killed_without_waiting_600_seconds(self):
        fake, state = self.fake_process(b"Warn : Haven't made progress in mpsse_flush() for 8090ms.\n")
        with patch('yolo_auto_jtag.subprocess.Popen', fake):
            with self.assertRaisesRegex(RuntimeError, '无进展'):
                self.transport.run('stall', ['init','shutdown'])
        self.assertTrue(state['killed'])

    def test_operation_timeout_also_kills_child(self):
        fake, state = self.fake_process(b'')
        with patch('yolo_auto_jtag.subprocess.Popen', fake), patch('yolo_auto_jtag.time.monotonic', side_effect=[0,41]):
            with self.assertRaisesRegex(RuntimeError, '超过 40 秒'):
                self.transport.run('timeout', ['init','shutdown'])
        self.assertTrue(state['killed'])


if __name__=='__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TransportTests))
    out = ROOT/'fusion/ti60_yolo_auto/validation/jtag_transport'
    out.mkdir(parents=True, exist_ok=True)
    failure=ROOT/'上板测试记录/YOLO_AUTO_同屏测试_20261027_193402_075241'
    paths = [Path(__file__), SW/'yolo_auto_jtag.py', SW/'yolo_auto_download.py',SW/'BEST_TEST_YOLO_AUTO_DOWNLOAD.launch',
             failure/'probe.bin',*[failure/('probe_try%d_readback.bin'%i) for i in (1,2,3)]]
    report = dict(complete=True,passed=result.wasSuccessful(),board_accessed=False,tests_run=result.testsRun,
        inputs_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    sys.exit(not result.wasSuccessful())
