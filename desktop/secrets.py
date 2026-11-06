"""Keep a GitHub token out of the planner database and out of text files.

Windows stores it in Credential Manager. If that cannot be written, Windows
stores a DPAPI blob instead. The token is never written as plain text. Other
systems do not store it.
"""
from __future__ import annotations

import os
from pathlib import Path

from desktop.errors import DesktopError

TARGET_NAME = "Align/GitHub"
TOKEN_MARK = "Align-Desktop-GitHub-Token"
DPAPI_NAME = "github-token.dpapi"


class SecretStore:
    def load(self) -> str:
        return ""

    def save(self, value: str) -> None:
        raise DesktopError("A GitHub token can be saved on Windows, in Credential Manager.")

    def clear(self) -> None:
        return


class MemorySecretStore(SecretStore):
    """Test double. It does not write a file."""

    def __init__(self) -> None:
        self.value = ""

    def load(self) -> str:
        return self.value

    def save(self, value: str) -> None:
        self.value = value

    def clear(self) -> None:
        self.value = ""


class UnavailableSecretStore(SecretStore):
    pass


def seal_token(token: str, protect) -> bytes:
    """Return protected bytes. Refuse a blob that still contains the token."""
    blob = protect(token.encode("utf-8"))
    raw = token.encode("utf-8")
    if not isinstance(blob, (bytes, bytearray)) or not blob or raw in blob:
        raise DesktopError("The GitHub token could not be protected.")
    return bytes(blob)


def _credential_write(token: str) -> None:
    import ctypes
    from ctypes import wintypes

    class Credential(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    blob = ctypes.create_string_buffer(token.encode("utf-8"))
    credential = Credential()
    credential.Type = 1
    credential.TargetName = TARGET_NAME
    credential.CredentialBlobSize = len(token.encode("utf-8"))
    credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_char))
    credential.Persist = 2
    credential.UserName = "Align"
    if not ctypes.windll.advapi32.CredWriteW(ctypes.byref(credential), 0):
        raise OSError("Credential Manager did not store the token.")


def _credential_read() -> str:
    import ctypes
    from ctypes import wintypes

    class Credential(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    pointer = ctypes.POINTER(Credential)()
    if not ctypes.windll.advapi32.CredReadW(TARGET_NAME, 1, 0, ctypes.byref(pointer)):
        return ""
    try:
        credential = pointer.contents
        size = int(credential.CredentialBlobSize)
        if size <= 0 or not credential.CredentialBlob:
            return ""
        return ctypes.string_at(credential.CredentialBlob, size).decode("utf-8")
    finally:
        ctypes.windll.advapi32.CredFree(pointer)


def _credential_delete() -> None:
    import ctypes

    ctypes.windll.advapi32.CredDeleteW(TARGET_NAME, 1, 0)


def _dpapi_protect(payload: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def fill(data: bytes) -> Blob:
        buffer = ctypes.create_string_buffer(data)
        item = Blob()
        item.cbData = len(data)
        item.pbData = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))
        item._buffer = buffer
        return item

    incoming = fill(payload)
    entropy = fill(TOKEN_MARK.encode("utf-8"))
    outgoing = Blob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(incoming), "Align", ctypes.byref(entropy), None, None, 0x01, ctypes.byref(outgoing)
    ):
        raise OSError("Windows could not protect the token.")
    try:
        return ctypes.string_at(outgoing.pbData, outgoing.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(outgoing.pbData)


def _dpapi_unprotect(payload: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def fill(data: bytes) -> Blob:
        buffer = ctypes.create_string_buffer(data)
        item = Blob()
        item.cbData = len(data)
        item.pbData = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))
        item._buffer = buffer
        return item

    incoming = fill(payload)
    entropy = fill(TOKEN_MARK.encode("utf-8"))
    outgoing = Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(incoming), None, ctypes.byref(entropy), None, None, 0x01, ctypes.byref(outgoing)
    ):
        raise OSError("Windows could not read the protected token.")
    try:
        return ctypes.string_at(outgoing.pbData, outgoing.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(outgoing.pbData)


class WindowsSecretStore(SecretStore):
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.blob_path = self.data_dir / DPAPI_NAME

    def load(self) -> str:
        try:
            token = _credential_read()
        except OSError:
            token = ""
        if token:
            return token
        if not self.blob_path.is_file():
            return ""
        try:
            return _dpapi_unprotect(self.blob_path.read_bytes()).decode("utf-8")
        except (OSError, UnicodeError):
            return ""

    def save(self, value: str) -> None:
        try:
            _credential_write(value)
        except OSError:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            sealed = seal_token(value, _dpapi_protect)
            temporary = self.blob_path.with_suffix(".dpapi.partial")
            temporary.write_bytes(sealed)
            temporary.replace(self.blob_path)
            return
        self.blob_path.unlink(missing_ok=True)

    def clear(self) -> None:
        try:
            _credential_delete()
        except OSError:
            pass
        self.blob_path.unlink(missing_ok=True)


def default_store(data_dir: Path) -> SecretStore:
    if os.name == "nt":
        return WindowsSecretStore(data_dir)
    return UnavailableSecretStore()
