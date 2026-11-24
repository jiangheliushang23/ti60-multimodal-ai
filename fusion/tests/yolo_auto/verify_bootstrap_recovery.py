"""Recovery policy tests: preserve integrity, bound reloads, exclude transfer errors."""
from pathlib import Path
import hashlib,json,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[3]
SW=ROOT/'fusion/demo_multimodal/software/standalone/tinyml_yolo_static'
sys.path.insert(0,str(SW))
from yolo_auto_recovery import BootstrapRecovery,recoverable_failure

class RecoveryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.output=Path(self.temp.name);self.actions=[]
  self.recovery=BootstrapRecovery(self.output,lambda:self.actions.append('reload') or {'flash_written':False},
    lambda:self.actions.append('identity'),notify=lambda _:None)
 def tearDown(self):self.temp.cleanup()
 def test_good_bootstrap_never_reloads(self):
  self.assertEqual(self.recovery.run('uart_bootstrap',lambda:91),91)
  self.assertFalse(self.recovery.used);self.assertEqual(self.actions,[])
 def test_actual_failed_log_is_recognized(self):
  path=ROOT/'上板测试记录/YOLO_AUTO_同屏测试_20261028_164129_574718/uart_loader_try3.log'
  self.assertTrue(recoverable_failure('uart_bootstrap',RuntimeError(path.read_text(encoding='utf8'))))
 def test_one_reload_rechecks_and_retries_before_transfer(self):
  calls=[]
  def action():
   calls.append(1)
   if len(calls)==1:raise RuntimeError('本块读回与写入数据不一致：loader.bin')
   return {'firmware_readback_exact':True}
  self.assertEqual(self.recovery.run('uart_bootstrap',action),{'firmware_readback_exact':True})
  self.assertEqual(self.actions,['reload','identity']);self.assertEqual(len(calls),2)
  self.assertTrue(json.loads((self.output/'bootstrap_recovery.json').read_text(encoding='utf8'))['events'][0]['retry_passed'])
 def test_persistent_failure_never_reports_success_or_reloads_twice(self):
  def failure():raise RuntimeError('本块读回与写入数据不一致')
  with self.assertRaises(RuntimeError):self.recovery.run('uart_bootstrap',failure)
  with self.assertRaises(RuntimeError):self.recovery.run('uart_bootstrap',failure)
  self.assertEqual(self.actions,['reload','identity']);self.assertFalse(self.recovery.events[0]['retry_passed'])
 def test_identity_mismatch_usb_and_application_errors_never_reload(self):
  messages=['当前 bit 缺少 EN01 网口接口','libusb open failed','串口下载应答超时。',
   '串口完整读回与固件不一致。','完整固件读回不一致，CPU 未启动。']
  for message in messages:self.assertFalse(recoverable_failure('uart_bootstrap',RuntimeError(message)))
  self.assertFalse(recoverable_failure('application',RuntimeError('本块读回与写入数据不一致')))
 def test_disabled_requires_manual_recovery(self):
  self.recovery.enabled=False
  def failure():raise RuntimeError('本块读回与写入数据不一致')
  with self.assertRaises(RuntimeError):self.recovery.run('uart_bootstrap',failure)
  self.assertEqual(self.actions,[])
 def test_failed_reprogram_does_not_retry_loader(self):
  calls=[]
  def failure():calls.append(1);raise RuntimeError('本块读回与写入数据不一致')
  def failed_program():raise RuntimeError('programming failed')
  self.recovery.reprogram=failed_program
  with self.assertRaisesRegex(RuntimeError,'programming failed'):self.recovery.run('uart_bootstrap',failure)
  self.assertEqual(calls,[1]);self.assertFalse(self.recovery.events[0]['bit_reloaded'])

if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RecoveryTests))
 out=ROOT/'fusion/ti60_yolo_auto/validation/bootstrap_recovery';out.mkdir(exist_ok=True)
 files=[Path(__file__),SW/'yolo_auto_recovery.py',SW/'yolo_auto_download.py',ROOT/'delivery/program_yolo_auto_bit.py']
 report=dict(complete=True,passed=result.wasSuccessful(),board_accessed=False,tests_run=result.testsRun,
  inputs_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
 (out/'software_result.json').write_text(json.dumps(report,indent=2),encoding='utf8')
 sys.exit(not result.wasSuccessful())
