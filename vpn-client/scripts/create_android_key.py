"""Create a local release signing identity once. Generated credentials are gitignored."""
import os
from pathlib import Path
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[1] / 'android'
properties = ROOT / 'signing.properties'
key = ROOT / 'reality-client.jks'
if properties.exists() or key.exists():
    if not properties.exists() or not key.exists():
        raise RuntimeError('Signing files are incomplete; restore the missing file before continuing')
    print('Existing signing identity preserved')
else:
    password = secrets.token_urlsafe(32)
    keytool = Path(os.environ['JAVA_HOME']) / 'bin/keytool.exe'
    environment = {**os.environ, 'REALITY_SIGN_PASSWORD': password}
    subprocess.run([str(keytool), '-genkeypair', '-keystore', str(key), '-storetype', 'JKS', '-alias', 'reality-client', '-keyalg', 'RSA', '-keysize', '3072', '-validity', '10000', '-dname', 'CN=Reality VPN, O=Reality Control', '-storepass:env', 'REALITY_SIGN_PASSWORD', '-keypass:env', 'REALITY_SIGN_PASSWORD'], check=True, env=environment)
    properties.write_text(f'storeFile=reality-client.jks\nstorePassword={password}\nkeyAlias=reality-client\nkeyPassword={password}\n', encoding='utf-8')
    print('Created local signing identity. Back up android/reality-client.jks and android/signing.properties securely for future APK updates.')
