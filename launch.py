"""Friendly launcher; the optional Wi-Fi password stays in this process only."""
import getpass
import os
from pathlib import Path
import runpy
import sys

if sys.version_info < (3, 10):
    sys.exit('Install Python 3.10 or later from https://www.python.org/downloads/windows/')

if '--network' in sys.argv and not os.environ.get('ALIGN_ADMIN_PASSWORD'):
    print('Wi-Fi mode: choose an Admin password for this run. It is not saved to disk.')
    password = getpass.getpass('Admin password (at least 8 characters): ')
    if len(password) < 8:
        sys.exit('Use at least 8 characters. Restart the launcher to try again.')
    confirmation = getpass.getpass('Confirm Admin password: ')
    if password != confirmation:
        sys.exit('Passwords did not match. Restart the launcher to try again.')
    os.environ['ALIGN_ADMIN_PASSWORD'] = password

port = os.environ.get('ALIGN_PORT', '8001')
if '--network' in sys.argv:
    try:
        from https_setup import issue_server_certificate
        cert_path, key_path, lan_ip = issue_server_certificate()
    except (ImportError, RuntimeError) as error:
        sys.exit(f'{error}\nRun Install Align Add-ons.bat and choose iPhone HTTPS certificate support, then try Wi-Fi mode again.')
    os.environ['ALIGN_SSL_CERT'] = str(cert_path)
    os.environ['ALIGN_SSL_KEY'] = str(key_path)
    print(f'On your iPhone use https://{lan_ip}:{port}/ on the same Wi-Fi.')
    admin_port = os.environ.get('ALIGN_ADMIN_PORT', '8003')
    print(f'On this PC, Admin: http://127.0.0.1:{admin_port}/admin')
    print('Use the PC-only Admin address above to connect iCloud. It is not exposed to Wi-Fi devices.')
    print('If Safari warns about the certificate, run Install Align Add-ons.bat and choose iPhone HTTPS certificate support.')
else:
    print(f'On this PC, open http://127.0.0.1:{port}/')
runpy.run_path(str(Path(__file__).with_name('app.py')), run_name='__main__')
