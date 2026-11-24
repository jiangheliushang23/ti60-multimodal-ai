"""Build the small, signed Android client with official Android SDK tools (no Gradle)."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
SDK = Path.home() / '.cache/ti60-android-sdk'
JAVA = Path(os.environ.get('TI60_JAVA', 'D:/Efinity/Efinity-RISCV-IDE/jre')) / 'bin'
PACKAGES = [('platform-35_r02.zip', '0bb560a90a7a2cbd0dd8348224d518b638fe7949', 'android-35/android.jar'),
            ('build-tools_r35_windows.zip', 'af059bb67cf7786f45ee0db85e2d24985df1b4b6', 'android-15/aapt2.exe')]


def fetch(package):
    name, digest, marker = package
    if (SDK / marker).exists():
        return
    SDK.mkdir(parents=True, exist_ok=True)
    archive = SDK / name
    if not archive.exists() or hashlib.sha1(archive.read_bytes()).hexdigest() != digest:
        print('Downloading official Android SDK:', name, flush=True)
        temp = archive.with_suffix('.part')
        with urllib.request.urlopen('https://dl.google.com/android/repository/' + name, timeout=45) as response, temp.open('wb') as output:
            shutil.copyfileobj(response, output)
        if hashlib.sha1(temp.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Official SDK checksum mismatch')
        temp.replace(archive)
    with zipfile.ZipFile(archive) as source:
        source.extractall(SDK)


def main():
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(fetch, PACKAGES))
    platform = SDK / 'android-35/android.jar'
    tools = SDK / 'android-15'
    if not (tools / 'aapt2.exe').exists():
        tools = next(p.parent for p in SDK.rglob('aapt2.exe'))
    out = HERE / 'build'
    dist = HERE / 'dist'
    for p in (out, dist, out / 'classes', out / 'dex'):
        p.mkdir(parents=True, exist_ok=True)
    logs = []

    def run(command):
        result = subprocess.run(list(map(str, command)), cwd=HERE, capture_output=True, text=True, encoding='utf8', errors='replace')
        logs.append(result.stdout + result.stderr)
        (out / 'build.log').write_text('\n'.join(logs), encoding='utf8')
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        return result.stdout

    run([tools / 'aapt2.exe', 'compile', '--dir', HERE / 'res', '-o', out / 'resources.zip'])
    run([tools / 'aapt2.exe', 'link', '-I', platform, '--manifest', HERE / 'AndroidManifest.xml',
         '--min-sdk-version', '26', '--target-sdk-version', '35', '--auto-add-overlay',
         '-o', out / 'resources.apk', out / 'resources.zip'])
    source = sorted((HERE / 'src').rglob('*.java'))
    run([JAVA / 'javac.exe', '-encoding', 'UTF-8', '-source', '8', '-target', '8', '-classpath', platform,
         '-d', out / 'classes', *source])
    run([JAVA / 'java.exe', '-cp', tools / 'lib/d8.jar', 'com.android.tools.r8.D8', '--lib', platform,
         '--min-api', '26', '--output', out / 'dex', *sorted((out / 'classes').rglob('*.class'))])
    unsigned = out / 'unsigned.apk'
    shutil.copyfile(out / 'resources.apk', unsigned)
    with zipfile.ZipFile(unsigned, 'a', compression=zipfile.ZIP_DEFLATED) as apk:
        for dex in (out / 'dex').glob('*.dex'):
            apk.write(dex, dex.name)
    run([tools / 'zipalign.exe', '-f', '4', unsigned, out / 'aligned.apk'])
    # Local deployment key is reused for updates; this APK is not a Play Store release.
    key = HERE / 'signing/local-install.p12'
    key.parent.mkdir(exist_ok=True)
    if not key.exists():
        run([JAVA / 'keytool.exe', '-genkeypair', '-keystore', key, '-storetype', 'PKCS12', '-storepass', 'ti60-local-install',
             '-keypass', 'ti60-local-install', '-alias', 'ti60', '-dname', 'CN=Ti60 Local Monitor', '-keyalg', 'RSA', '-keysize', '2048', '-validity', '3650'])
    apk = dist / 'Ti60-Fall-Monitor.apk'
    run([JAVA / 'java.exe', '-jar', tools / 'lib/apksigner.jar', 'sign', '--ks', key, '--ks-pass', 'pass:ti60-local-install',
         '--out', apk, out / 'aligned.apk'])
    signature = run([JAVA / 'java.exe', '-jar', tools / 'lib/apksigner.jar', 'verify', '--verbose', '--print-certs', apk])
    run([tools / 'zipalign.exe', '-c', '4', apk])
    manifest = run([tools / 'aapt2.exe', 'dump', 'badging', apk])
    report = dict(complete=True, passed=True, device_tested=False, android_min=26, android_target=35,
                  package='cn.ti60.fallmonitor', apk_bytes=apk.stat().st_size,
                  apk_sha256=hashlib.sha256(apk.read_bytes()).hexdigest(), signature=signature, manifest=manifest)
    (dist / 'build_result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    (dist / 'Ti60-Fall-Monitor.apk.sha256').write_text(report['apk_sha256'] + '  Ti60-Fall-Monitor.apk\n', encoding='ascii')
    print('ANDROID_APK_READY', apk, report['apk_bytes'], flush=True)


if __name__ == '__main__':
    main()
