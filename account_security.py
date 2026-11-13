"""Two-step codes and the public breach check. No third-party TOTP package."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
import urllib.request
from urllib.parse import quote


def generate_secret():
    return base64.b32encode(os.urandom(20)).decode('ascii').rstrip('=')


def totp(secret, when=None, step=30):
    padded = secret.upper() + '=' * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    counter = int((time.time() if when is None else when) // step)
    digest = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 15
    number = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7fffffff
    return str(number % 1_000_000).zfill(6)


def verify_totp(secret, code, when=None):
    value = str(code or '').strip()
    if len(value) != 6 or not value.isdigit() or not secret:
        return False
    moment = time.time() if when is None else when
    return any(hmac.compare_digest(totp(secret, moment + offset), value) for offset in (-30, 0, 30))


def provisioning_uri(secret, email):
    label = quote(str(email or 'align'))
    return f'otpauth://totp/Align:{label}?secret={secret}&issuer=Align&digits=6&period=30'


def password_breached(password, fetch=None):
    """True when the password is in the Have I Been Pwned range list.

    Set ALIGN_BREACH_CHECK=0 to skip the lookup. A failed lookup is treated as
    a breach check failure so a password is not saved unverified.
    """
    if os.environ.get('ALIGN_BREACH_CHECK', '1') == '0':
        return False
    digest = hashlib.sha1(str(password).encode('utf-8')).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    fetch = fetch or _hibp_fetch
    try:
        body = fetch(prefix)
    except Exception as error:
        raise RuntimeError('Password check is unavailable. Try again shortly.') from error
    for line in body.splitlines():
        parts = line.split(':')
        if len(parts) >= 2 and hmac.compare_digest(parts[0].strip().upper(), suffix):
            return True
    return False


def _hibp_fetch(prefix):
    request = urllib.request.Request(
        'https://api.pwnedpasswords.com/range/' + prefix,
        headers={'Add-Padding': 'true', 'User-Agent': 'Align-password-check'},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.read(200_000).decode('utf-8', errors='replace')
