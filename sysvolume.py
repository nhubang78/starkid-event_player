"""Âm lượng chính của sound card (Windows Core Audio — IAudioEndpointVolume), gọi bằng ctypes.

Giá trị 0..1 trùng với con số trên thanh âm lượng Windows (0,34 = 34).
Không cần thư viện ngoài; trên hệ điều hành khác hoặc khi lỗi thì available() = False.
"""
import ctypes
import sys
from ctypes import POINTER, byref, c_float, c_int, c_long, c_uint, c_void_p, c_wchar_p

_OK = sys.platform == "win32"


class _GUID(ctypes.Structure):
    _fields_ = [("d1", ctypes.c_uint32), ("d2", ctypes.c_uint16), ("d3", ctypes.c_uint16),
                ("d4", ctypes.c_ubyte * 8)]

    def __init__(self, s):
        super().__init__()
        if _OK:
            ctypes.oledll.ole32.CLSIDFromString(c_wchar_p("{" + s + "}"), byref(self))


CLSID_MMDeviceEnumerator = "BCDE0395-E52F-467C-8E3D-C4579291692E"
IID_IMMDeviceEnumerator = "A95664D2-9614-4F35-A746-DE8DB63617E6"
IID_IAudioEndpointVolume = "5CDF2C82-841E-4546-9722-0CF74078229A"
CLSCTX_ALL = 0x17
E_RENDER, E_MULTIMEDIA = 0, 1


def _call(obj, index, *args, argtypes=()):
    """Gọi hàm thứ `index` trong vtable của đối tượng COM; trả về HRESULT."""
    vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
    fn = ctypes.WINFUNCTYPE(c_long, c_void_p, *argtypes)(vtbl[index])
    return fn(obj, *args)


def _release(obj):
    if obj:
        _call(obj, 2)


class SystemVolume:
    """Điều khiển âm lượng một thiết bị ra (theo mã thiết bị của Qt), mặc định = thiết bị mặc định."""

    def __init__(self):
        self._enum = None
        self._vol = None
        self.device_id = None
        if not _OK:
            return
        try:
            ctypes.windll.ole32.CoInitializeEx(None, 2)   # đã khởi tạo rồi thì trả về S_FALSE — bỏ qua
            p = c_void_p()
            hr = ctypes.windll.ole32.CoCreateInstance(byref(_GUID(CLSID_MMDeviceEnumerator)), None, CLSCTX_ALL,
                                                      byref(_GUID(IID_IMMDeviceEnumerator)), byref(p))
            if hr == 0:
                self._enum = p
        except OSError:
            self._enum = None

    def available(self):
        return self._vol is not None

    def set_device(self, device_id: str = ""):
        """device_id: chuỗi mã thiết bị (QAudioDevice.id()); "" = thiết bị ra mặc định của Windows."""
        if self._enum is None:
            return False
        _release(self._vol)
        self._vol = None
        dev = c_void_p()
        hr = -1
        if device_id:
            hr = _call(self._enum, 5, c_wchar_p(device_id), byref(dev), argtypes=(c_wchar_p, POINTER(c_void_p)))
        if hr != 0:
            hr = _call(self._enum, 4, E_RENDER, E_MULTIMEDIA, byref(dev),
                       argtypes=(c_int, c_int, POINTER(c_void_p)))
        if hr != 0 or not dev:
            return False
        vol = c_void_p()
        hr = _call(dev, 3, byref(_GUID(IID_IAudioEndpointVolume)), CLSCTX_ALL, None, byref(vol),
                   argtypes=(POINTER(_GUID), c_uint, c_void_p, POINTER(c_void_p)))
        _release(dev)
        if hr == 0 and vol:
            self._vol = vol
            self.device_id = device_id
            return True
        return False

    def get(self):
        """Âm lượng 0..1, hoặc None nếu không đọc được."""
        if self._vol is None:
            return None
        v = c_float()
        if _call(self._vol, 9, byref(v), argtypes=(POINTER(c_float),)) != 0:
            return None
        return max(0.0, min(1.0, v.value))

    def set(self, value: float):
        if self._vol is None:
            return False
        v = max(0.0, min(1.0, float(value)))
        return _call(self._vol, 7, c_float(v), None, argtypes=(c_float, c_void_p)) == 0

    def muted(self):
        if self._vol is None:
            return False
        m = ctypes.c_int()
        return _call(self._vol, 15, byref(m), argtypes=(POINTER(ctypes.c_int),)) == 0 and bool(m.value)

    def set_mute(self, on: bool):
        if self._vol is not None:
            _call(self._vol, 14, int(bool(on)), None, argtypes=(c_int, c_void_p))
