"""Soi nhịp: phân tích bài nhạc (nhạc cụ theo dải tần, phách, ô nhịp, đoạn INTRO/BUILD/DROP/BREAK/OUTRO,
điểm Drop) và cửa sổ hiển thị chi tiết để chỉnh kênh (CUE, IN/OUT, LOOP, Hot Cue).

Nhận diện nhạc cụ dựa trên năng lượng + nhịp gõ (onset) của từng dải tần — không phải AI tách nhạc:
Kick / Snare / Hi-hat / Bass / phách / ô nhịp khá tin cậy với nhạc có trống; Clap và Giọng hát là ước lượng.
"""
import os
import threading

import numpy as np
from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from theme import T, channel_dot

VERSION = 7
SR, NFFT, HOP = 32000, 2048, 512
FPS = SR / HOP                       # 62,5 khung / giây (16 ms)
LAYERS = [("kick", "Kick", "#f59e0b"), ("snare", "Snare", "#38bdf8"), ("clap", "Clap", "#22c55e"),
          ("hat", "Hi-hat", "#e879f9"), ("bass", "Bass", "#a78bfa"), ("vocal", "Giọng hát", "#fb7185")]
MARKS = [("beats", "Phách", "#94a3b8"), ("bars", "Ô nhịp", "#cbd5e1"), ("sections", "Đoạn", "#3b82f6"),
         ("drops", "◆ Điểm Drop", "#ef4444")]
SECTION_COLORS = {"INTRO": "#3b82f6", "BUILD": "#f59e0b", "DROP": "#ef4444", "BREAK": "#64748b", "OUTRO": "#8b5cf6"}
SECTION_CODES = ["INTRO", "BUILD", "DROP", "BREAK", "OUTRO"]
BANDS = {"sub": (40, 120), "bass": (50, 250), "body": (150, 400), "m1": (800, 2500), "h1": (3000, 7000),
         "mh": (800, 7000), "hat": (8000, 15000), "voc": (300, 3400), "all": (30, 15000)}
T0 = NFFT / 2 / HOP          # khung phân tích được gắn nhãn ở giữa cửa sổ (= 2 khung = 32 ms)


# ================================================================== phân tích
def _cache_path(path):
    from waveform import _cache_file
    f = _cache_file(path)
    return f[:-len(".wav.peaks")] + f".beat{VERSION}.npz" if f else None


def _decode(path, progress, cancel):
    import av
    chunks = []
    with av.open(path) as c:
        st = next((s for s in c.streams if s.type == "audio"), None)
        if st is None:
            return None
        st.thread_type = "AUTO"
        total = (float(st.duration * st.time_base) if st.duration else (c.duration or 0) / 1e6) * SR
        rs = av.AudioResampler(format="flt", layout="mono", rate=SR)
        got, k = 0, 0
        for fr in c.decode(st):
            for r in rs.resample(fr):
                a = r.to_ndarray().reshape(-1)
                chunks.append(a)
                got += a.size
            k += 1
            if k % 300 == 0:
                if cancel.is_set():
                    return None
                if total:
                    progress(int(35 * got / total), "Đang giải mã bài...")
        for r in rs.resample(None):
            chunks.append(r.to_ndarray().reshape(-1))
    if not chunks:
        return None
    return np.clip(np.concatenate(chunks).astype(np.float32), -1.0, 1.0)


def _band_energies(x, progress, cancel):
    if x.size < NFFT:
        x = np.pad(x, (0, NFFT - x.size))
    nfr = 1 + (x.size - NFFT) // HOP
    win = np.hanning(NFFT).astype(np.float32)
    freqs = np.fft.rfftfreq(NFFT, 1 / SR)
    idx = {k: (int(np.searchsorted(freqs, a)), int(np.searchsorted(freqs, b))) for k, (a, b) in BANDS.items()}
    E = {k: np.zeros(nfr, np.float32) for k in BANDS}
    flat = np.zeros(nfr, np.float32)
    offs = np.arange(NFFT)
    step = 768
    va, vb = idx["voc"]
    for f0 in range(0, nfr, step):
        if cancel.is_set():
            return None
        f1 = min(nfr, f0 + step)
        frames = x[(np.arange(f0, f1) * HOP)[:, None] + offs] * win
        P = np.abs(np.fft.rfft(frames, axis=1)).astype(np.float32) ** 2
        for k, (a, b) in idx.items():
            E[k][f0:f1] = P[:, a:b].sum(axis=1)
        v = P[:, va:vb] + 1e-12
        flat[f0:f1] = np.exp(np.mean(np.log(v), axis=1)) / np.mean(v, axis=1)
        progress(35 + int(45 * f1 / nfr), "Đang phân tích dải tần...")
    n = min(nfr, x.size // HOP)
    peak = np.zeros(nfr, np.float32)
    blk = x[:n * HOP].reshape(n, HOP)
    peak[:n] = np.sqrt((blk * blk).mean(axis=1))          # RMS mỗi 16 ms (rõ đoạn mạnh / nhẹ hơn đỉnh)
    peak /= float(np.percentile(peak[:max(1, n)], 99.5)) + 1e-9
    np.clip(peak, 0, 1, out=peak)
    return E, flat, peak


def _flux(E):
    ref = float(np.percentile(E, 95)) + 1e-12
    e = np.log1p(E / ref * 100)
    return np.maximum(0.0, np.diff(e, prepend=e[0])).astype(np.float32)


def _movavg(x, n):
    n = max(1, min(int(n), x.size))          # bài rất ngắn: cửa sổ không dài hơn dữ liệu
    if x.size == 0:
        return x
    return np.convolve(x, np.ones(n) / n, mode="same")


def _onsets(flux, delta, gap_s):
    """Chọn đỉnh của flux vượt ngưỡng thích nghi; cách nhau ít nhất gap_s giây."""
    thr = _movavg(flux, FPS * 0.4) + delta * (float(np.percentile(flux, 90)) + 1e-9)
    is_pk = np.zeros(flux.size, bool)
    is_pk[1:-1] = (flux[1:-1] > flux[:-2]) & (flux[1:-1] >= flux[2:])
    cand = np.nonzero(is_pk & (flux > thr))[0]
    gap = max(1, int(gap_s * FPS))
    out = []
    for i in cand:
        if out and i - out[-1] < gap:
            if flux[i] > flux[out[-1]]:
                out[-1] = i
            continue
        out.append(int(i))
    return np.array(out, dtype=np.int32)


def _tempo(env):
    """(bước phách tính bằng khung, pha khung) từ đường onset."""
    m = env.size
    env = env - _movavg(env, FPS * 1.0)
    env = np.maximum(0, env)
    spec = np.fft.rfft(env, 2 * m)
    ac = np.fft.irfft(spec * np.conj(spec))[:m]
    lmin, lmax = int(60 * FPS / 200), int(60 * FPS / 60) + 1
    if lmax + 2 >= m:
        return 0.0, 0
    lags = np.arange(lmin, lmax)
    bpms = 60 * FPS / lags
    score = ac[lmin:lmax] * np.exp(-0.5 * (np.log2(bpms / 120.0) / 0.9) ** 2)
    lag = float(lags[int(np.argmax(score))])
    if 60 * FPS / lag < 100:
        h = int(round(lag / 2))
        if h - 1 >= lmin and float(ac[h - 1:h + 2].max()) >= 0.6 * float(ac[int(round(lag))]):
            lag = lag / 2
    best, best_l, best_p = -1.0, lag, 0
    for L in np.linspace(lag * 0.985, lag * 1.015, 61):
        nb = int((m - 1) // L)
        if nb < 4:
            continue
        ph = np.arange(int(np.ceil(L)))[:, None]
        idx = np.minimum((ph + np.arange(nb)[None, :] * L).astype(int), m - 1)
        sums = env[idx].sum(axis=1)
        p = int(np.argmax(sums))
        if sums[p] > best:
            best, best_l, best_p = float(sums[p]), float(L), p
    return best_l, best_p


def _segments(mask, min_len, max_gap):
    segs = []
    i, n = 0, mask.size
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            if segs and i - segs[-1][1] <= max_gap:
                segs[-1][1] = j
            else:
                segs.append([i, j])
            i = j
        else:
            i += 1
    return [s for s in segs if s[1] - s[0] >= min_len]


def load_analysis(cp):
    """Đọc kết quả phân tích đã lưu (file .npz); None nếu chưa có / hỏng."""
    if cp and os.path.isfile(cp):
        try:
            with np.load(cp, allow_pickle=False) as z:
                return {k: z[k] for k in z.files}
        except (OSError, ValueError):
            pass
    return None


def analyze(path, progress=lambda pc, msg: None, cancel=None, cache_path=None):
    cancel = cancel or threading.Event()
    cp = cache_path or _cache_path(path)
    if cp and os.path.isfile(cp):
        try:
            with np.load(cp, allow_pickle=False) as z:
                return {k: z[k] for k in z.files}
        except (OSError, ValueError):
            pass
    x = _decode(path, progress, cancel)
    if x is None:
        return None
    r = _band_energies(x, progress, cancel)
    if r is None:
        return None
    E, flat, peak = r
    progress(82, "Đang nhận diện nhạc cụ...")
    fx = {k: _flux(E[k]) for k in ("sub", "bass", "body", "m1", "h1", "mh", "hat", "all")}
    kick = _onsets(fx["sub"], 0.45, 0.18)
    # kick thật: đủ mạnh so với các kick lân cận (±0,5 s) và có năng lượng dải trầm thật sự
    if kick.size:
        fs_ = fx["sub"]
        w = int(FPS * 0.5)
        sub_ref = float(np.percentile(E["sub"], 95)) + 1e-12
        keep = [i for i in kick if fs_[i] >= 0.45 * fs_[max(0, i - w):i + w + 1].max()
                and E["sub"][min(i + 1, fs_.size - 1)] >= 0.05 * sub_ref]
        kick = np.array(keep, np.int32)
    hat = _onsets(fx["hat"], 0.35, 0.06)
    bass = _onsets(fx["bass"], 0.35, 0.15)
    # Snare / Clap: tiếng gõ ở 0,8-7 kHz. Phân loại theo hình dạng phổ của tiếng gõ:
    #   chỉ xèo ở dải rất cao (> 8 kHz) -> hi-hat (bỏ qua); tập trung 0,8-2,5 kHz -> clap; trải rộng -> snare
    #   (so năng lượng TĂNG THÊM tuyệt đối của từng dải, chia theo bề rộng dải -> mật độ năng lượng)
    snr_l, clap_l = [], []
    nE = E["all"].size

    def rise(band, i):
        a, b = BANDS[band]
        e = E[band]
        return max(0.0, float(e[min(nE - 1, i + 1)]) - float(e[max(0, i - 2)])) / (b - a)

    for i in _onsets(fx["mh"], 0.45, 0.10):
        dm, dh, dhat = rise("m1", i), rise("h1", i), rise("hat", i)
        if dhat > 6 * max(dm, dh, 1e-30):          # gần như chỉ có tiếng xèo rất cao -> hi-hat
            continue
        if dm > 4 * dh:                             # dồn ở 0,8-2,5 kHz -> clap
            clap_l.append(i)
        else:
            snr_l.append(i)
    snr, clap = np.array(snr_l, np.int32), np.array(clap_l, np.int32)
    # Giọng hát (ước lượng): dải 300-3400 Hz chiếm ưu thế, có cao độ (ít "phẳng"), đủ to
    ratio = E["voc"] / (E["all"] + 1e-12)
    loud = E["voc"] > np.percentile(E["voc"], 35)
    score = ratio * (1 - flat)
    vthr = np.percentile(score[loud], 55) if loud.any() else 1.0
    vmask = (score > vthr) & loud
    vmask = _movavg(vmask.astype(np.float32), FPS * 0.3) > 0.5
    vocal = _segments(vmask, int(FPS * 0.35), int(FPS * 0.2))
    # phách / ô nhịp
    progress(90, "Đang dò phách và ô nhịp...")
    env = 1.5 * fx["sub"] + fx["mh"] + 0.5 * fx["hat"] + 0.5 * fx["all"]
    period, phase = _tempo(env)
    nfr = E["all"].size
    if period > 0:
        beats_f = np.arange(phase, nfr, period)
        bi = np.minimum(beats_f.astype(int), nfr - 1)
        edges_b = np.append(bi, nfr)
        e_beat = np.array([np.log10(E["all"][a:max(a + 1, b)].mean() + 1e-12) for a, b in zip(edges_b[:-1], edges_b[1:])])
        jump = np.maximum(0.0, np.diff(e_beat, prepend=e_beat[:1]))
        jump = jump / (jump.max() + 1e-9)
        kick_env = _movavg(fx["sub"], 3)
        kick_env = kick_env / (kick_env.max() + 1e-9)
        bass_on = np.zeros(nfr, np.float32)
        bass_on[bass] = 1.0
        score = [3.0 * jump[p::4].sum() + kick_env[bi[p::4]].sum() * 0.3 + bass_on[np.minimum(bi[p::4] + 1, nfr - 1)].sum() * 0.2
                 for p in range(4)]
        down = int(np.argmax(score))
        bars_f = beats_f[down::4]
        if bars_f.size and bars_f[0] - 4 * period > -period * 0.5:
            bars_f = np.concatenate(([max(0.0, bars_f[0] - 4 * period)], bars_f))
        bpm = 60 * FPS / period
    else:
        beats_f = bars_f = np.zeros(0)
        bpm = 0.0
    # đoạn: năng lượng mỗi ô nhịp
    sec_s, sec_e, sec_c, drops = [], [], [], []
    if bars_f.size >= 4:
        edges = np.append(bars_f, nfr).astype(int)
        lev = np.array([np.log10(E["all"][a:max(a + 1, b)].mean() + 1e-12) for a, b in zip(edges[:-1], edges[1:])])
        kd = np.array([((kick >= a) & (kick < b)).sum() for a, b in zip(edges[:-1], edges[1:])], float)
        lev = lev + 0.15 * np.minimum(kd, 4)
        lo, hi = np.percentile(lev, 10), np.percentile(lev, 90)
        hi_t, lo_t = lo + 0.62 * (hi - lo), lo + 0.3 * (hi - lo)
        st = np.where(lev >= hi_t, 2, np.where(lev <= lo_t, 0, 1))
        runs = []
        for i, s in enumerate(st):
            if runs and runs[-1][0] == s:
                runs[-1][2] = i + 1
            else:
                runs.append([int(s), i, i + 1])
        merged = []                                      # đoạn ngắn hơn 4 ô nhịp -> gộp vào đoạn trước
        for r in runs:
            if merged and (r[2] - r[1] < 4):
                merged[-1][2] = r[2]
            elif merged and merged[-1][0] == r[0]:
                merged[-1][2] = r[2]
            else:
                merged.append(r)
        def rising(a, b):                                # năng lượng tăng dần trong đoạn -> BUILD
            seg = lev[a:b]
            return seg.size >= 2 and float(seg[-max(1, seg.size // 3):].mean() - seg[:max(1, seg.size // 3)].mean()) >                 0.08 * float(hi - lo)

        drop_idx = [i for i, r in enumerate(merged) if r[0] == 2]
        first_d = drop_idx[0] if drop_idx else len(merged)
        last_d = drop_idx[-1] if drop_idx else -1
        for i, (s, a, b) in enumerate(merged):
            if s == 2:
                lab = "DROP"
            elif i < first_d:
                lab = "BUILD" if (s == 1 and i == first_d - 1 and rising(a, b)) else "INTRO"
            elif i > last_d:
                lab = "OUTRO"
            else:
                lab = "BUILD" if (s == 1 and i + 1 < len(merged) and merged[i + 1][0] == 2
                                  and rising(a, b)) else "BREAK"
            sec_s.append(edges[a])
            sec_e.append(edges[b])
            sec_c.append(SECTION_CODES.index(lab))
        for i, r in enumerate(merged):
            if r[0] == 2 and (i == 0 or merged[i - 1][0] != 2):
                drops.append(edges[r[1]])
    # Clap thường rơi đúng phách (phách 2 và 4): giữ tiếng gõ gần phách và đủ mạnh
    if clap.size and beats_f.size:
        near = np.abs(clap[:, None] - beats_f[None, :]).min(axis=1) <= 4
        strong = fx["m1"][clap] >= np.percentile(fx["m1"][clap], 60)
        clap = clap[near & strong]
    progress(98, "Đang lưu kết quả...")
    ms = 1000.0 / FPS
    res = {
        "version": np.array(VERSION), "duration": np.array(x.size * 1000.0 / SR), "fps": np.array(FPS),
        "peak": peak.astype(np.float16), "bpm": np.array(round(bpm, 1)),
        "beats": ((beats_f + T0) * ms).astype(np.float64), "bars": ((bars_f + T0) * ms).astype(np.float64),
        "sec_s": (np.array(sec_s, float) + T0) * ms, "sec_e": (np.array(sec_e, float) + T0) * ms,
        "sec_c": np.array(sec_c, np.int8),
        "drops": (np.array(drops, float) + T0) * ms,
        "vocal": ((np.array(vocal, float).reshape(-1, 2) + T0) * ms),
    }
    sh = int(T0)
    for key, band in (("kick", "sub"), ("snare", "h1"), ("clap", "m1"), ("hat", "hat"), ("bass", "bass")):
        env = np.sqrt(E[band] / (np.percentile(E[band], 98) + 1e-12))
        env = np.concatenate((np.zeros(sh, env.dtype), env[:-sh] if sh else env))
        res["env_" + key] = np.clip(env, 0, 1).astype(np.float16)
    for key, arr in (("kick", kick), ("snare", snr), ("clap", clap), ("hat", hat), ("bass", bass)):
        res["on_" + key] = (arr.astype(np.float64) + T0) * ms
    if cp:
        try:
            np.savez_compressed(cp + ".tmp.npz", **res)
            os.replace(cp + ".tmp.npz", cp)
        except OSError:
            pass
    return res


def _child_analyze(path, cp):
    """Chạy trong TIẾN TRÌNH PHỤ (PyAV không chạy cùng tiến trình với trình phát nhạc): phân tích + lưu .npz."""
    try:
        r = analyze(path, cache_path=cp)
        return None if r is None else "ok"
    except Exception as e:
        return "error: " + str(e)


class BeatAnalyzer(QObject):
    progress = Signal(int, str)
    done = Signal(object)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path
        self._fut = None
        self._stopped = False
        self._cp = _cache_path(path)
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._poll)
        self._ticks = 0

    def start(self):
        r = load_analysis(self._cp)
        if r is not None:
            QTimer.singleShot(0, lambda: self._emit(r))
            return
        from waveform import decode_pool
        try:
            self._fut = decode_pool().submit(_child_analyze, self.path, self._cp)
        except Exception as e:
            msg = str(e)
            QTimer.singleShot(0, lambda: self._emit({"error": msg}))
            return
        self._timer.start()

    def stop(self):
        self._stopped = True
        self._timer.stop()

    def _poll(self):
        self._ticks += 1
        if self._fut is None:
            return
        if not self._fut.done():
            if not self._stopped:
                self.progress.emit(min(95, self._ticks * 4), "Đang phân tích bài...")
            return
        self._timer.stop()
        try:
            res = self._fut.result()
        except Exception as e:
            res = "error: " + str(e)
        if res == "ok":
            self._emit(load_analysis(self._cp))
        else:
            self._emit({"error": res or "không đọc được file"})

    def _emit(self, r):
        if not self._stopped:
            try:
                self.done.emit(r)
            except RuntimeError:
                pass


# ================================================================== khung vẽ
class BeatView(QWidget):
    LEFT = 84
    SEC_H, RULER_H, LANE_H = 24, 20, 30

    seekRequested = Signal(int)
    playRequested = Signal(int)
    dropClicked = Signal(int)
    selectionChanged = Signal(object)

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(360)
        self.a = None
        self.duration = 1
        self.vs, self.ve = 0, 1
        self.pos = 0
        self.show = {k: True for k, *_ in LAYERS + MARKS}
        self.start_ms = self.end_ms = 0
        self.cues, self.loop = [], (0, 0, False)
        self.sel = None
        self.played = QColor("#f59e0b")
        self.message = "Đang phân tích..."
        self._rdrag = None
        self.hover = None

    def set_analysis(self, a):
        self.a = a
        if a is not None and "peak" in a:
            self.duration = max(1, int(float(a["duration"])))
            self.vs, self.ve = 0, self.duration
            self.message = ""
        self.update()

    # ---------- toạ độ
    def wave_rect(self):
        lanes = sum(1 for k, *_ in LAYERS if self.show[k])
        top = self.SEC_H + self.RULER_H + 4
        bottom = self.height() - lanes * self.LANE_H - 8
        return QRectF(self.LEFT, top, self.width() - self.LEFT - 10, max(60, bottom - top))

    def x_of(self, ms):
        r = self.wave_rect()
        return r.left() + (ms - self.vs) / max(1, self.ve - self.vs) * r.width()

    def ms_of(self, x):
        r = self.wave_rect()
        return int(self.vs + (x - r.left()) / max(1, r.width()) * (self.ve - self.vs))

    def set_view(self, vs, ve):
        span = max(1000, min(self.duration, int(ve - vs)))
        vs = max(0, min(int(vs), self.duration - span))
        self.vs, self.ve = vs, vs + span
        self.update()

    # ---------- vẽ
    def _cols(self, arr, w):
        """Giá trị lớn nhất của arr (mỗi khung 16 ms) trên từng cột điểm ảnh trong khung xem."""
        n = arr.size
        fms = 1000.0 / FPS
        i0, i1 = self.vs / fms, self.ve / fms
        edges = np.clip(np.linspace(i0, i1, w + 1).astype(int), 0, n - 1)
        if (i1 - i0) / max(1, w) >= 1:
            return np.maximum.reduceat(arr.astype(np.float32), edges[:-1])
        return arr[edges[:-1]].astype(np.float32)

    def _lanes_bottom(self):
        r = self.wave_rect()
        return r.bottom() + 6 + sum(1 for k, *_ in LAYERS if self.show[k]) * self.LANE_H

    def _static_key(self):
        import theme
        r = self.wave_rect()
        return (self.vs, self.ve, self.width(), self.height(), tuple(sorted(self.show.items())), id(self.a),
                theme.current(), self.played.name(), self.devicePixelRatioF(), int(r.width()))

    def _pixmap(self):
        from PySide6.QtGui import QPixmap
        dpr = self.devicePixelRatioF()
        pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        return pm

    def _wave_lines(self, p, color):
        """Vẽ sóng (RMS) bằng các nét dọc — nhanh hơn rất nhiều so với đường gồm nhiều hình chữ nhật."""
        from PySide6.QtCore import QLineF
        r = self.wave_rect()
        w = int(r.width())
        pk = self._cols(self.a["peak"], w)
        mid, half = r.center().y(), r.height() / 2 - 2
        lines = [QLineF(r.left() + i + .5, mid - float(pk[i]) * half, r.left() + i + .5, mid + float(pk[i]) * half + 1)
                 for i in range(w)]
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setPen(QPen(color, 1))
        p.drawLines(lines)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    def _render_static(self):
        """Phần không đổi theo đầu phát: đoạn, thước ô nhịp, lưới, sóng (màu nhạt), các dải nhạc cụ."""
        pm = self._pixmap()
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        a = self.a
        r = self.wave_rect()
        H = self.height()
        w = int(r.width())
        span = self.ve - self.vs
        f = QFont("Segoe UI")
        f.setPixelSize(11)
        f.setBold(True)
        p.setFont(f)
        # đoạn
        if self.show["sections"]:
            for s, e, c in zip(a["sec_s"], a["sec_e"], a["sec_c"]):
                if e < self.vs or s > self.ve:
                    continue
                lab = SECTION_CODES[int(c)]
                x0, x1 = max(r.left(), self.x_of(s)), min(r.right(), self.x_of(e))
                col = QColor(SECTION_COLORS[lab])
                bg = QColor(col)
                bg.setAlpha(55)
                p.fillRect(QRectF(x0, 2, x1 - x0, self.SEC_H - 4), bg)
                p.fillRect(QRectF(x0, 2, 3, self.SEC_H - 4), col)
                if x1 - x0 > 44:
                    p.setPen(col.lighter(130))
                    p.drawText(QRectF(x0 + 8, 2, x1 - x0 - 10, self.SEC_H - 4),
                               Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, lab)
        # thước số ô nhịp
        bars = a["bars"]
        ry = self.SEC_H
        f.setPixelSize(10)
        p.setFont(f)
        if bars.size:
            px_bar = (bars[1] - bars[0]) / span * r.width() if bars.size > 1 else 999
            every = next((k for k in (1, 2, 4, 8, 16, 32, 64) if px_bar * k >= 24), 64)
            for i, b in enumerate(bars):
                if b < self.vs or b > self.ve:
                    continue
                x = self.x_of(b)
                p.setPen(QPen(QColor(T["wave_ruler"]), 1))
                p.drawLine(QPointF(x, ry + 12), QPointF(x, ry + self.RULER_H))
                if i % every == 0:
                    p.setPen(QColor(T["text_dim"]))
                    p.drawText(QPointF(x + 2, ry + 11), str(i + 1))
        p.setClipRect(QRectF(r.left(), 0, r.width(), H))
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        if self.show["beats"] and a["beats"].size > 1:
            bpx = (a["beats"][1] - a["beats"][0]) / span * r.width()
            if bpx >= 4:
                c = QColor(T["text_faint"])
                c.setAlpha(70)
                p.setPen(QPen(c, 1))
                for b in a["beats"]:
                    if self.vs <= b <= self.ve:
                        x = self.x_of(b)
                        p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
        if self.show["bars"]:
            c = QColor(T["text_dim"])
            c.setAlpha(110)
            p.setPen(QPen(c, 1))
            for b in bars:
                if self.vs <= b <= self.ve:
                    x = self.x_of(b)
                    p.drawLine(QPointF(x, r.top()), QPointF(x, H - 4))
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        dim = QColor(self.played)
        dim.setAlpha(110)
        self._wave_lines(p, dim)
        p.setClipping(False)
        # dải nhạc cụ
        y = r.bottom() + 6
        f.setPixelSize(12)
        p.setFont(f)
        for key, name, col in LAYERS:
            if not self.show[key]:
                continue
            c = QColor(col)
            p.setPen(c)
            p.drawText(QRectF(8, y, self.LEFT - 10, self.LANE_H), Qt.AlignmentFlag.AlignVCenter, name)
            p.setPen(QPen(QColor(T["wave_grid"]), 1))
            p.drawLine(QPointF(r.left(), y + self.LANE_H), QPointF(r.right(), y + self.LANE_H))
            p.save()
            p.setClipRect(QRectF(r.left(), y, r.width(), self.LANE_H))
            cy, hh = y + self.LANE_H / 2, self.LANE_H / 2 - 4
            if key == "vocal":
                p.setPen(QPen(c, 1))
                p.setBrush(QColor(c.red(), c.green(), c.blue(), 60))
                for s, e in a["vocal"]:
                    if e >= self.vs and s <= self.ve:
                        p.drawRect(QRectF(self.x_of(s), cy - hh + 2, max(2.0, self.x_of(e) - self.x_of(s)), 2 * hh - 4))
            else:
                if key != "clap":
                    env = self._cols(a["env_" + key], w)
                    xs = r.left() + np.arange(w)
                    top_pts = [QPointF(float(xs[i]), cy - float(env[i]) * hh) for i in range(w)]
                    bot_pts = [QPointF(float(xs[i]), cy + float(env[i]) * hh) for i in range(w - 1, -1, -1)]
                    c2 = QColor(col)
                    c2.setAlpha(150)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(c2)
                    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                    p.drawPolygon(QPolygonF(top_pts + bot_pts))
                    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                ons = a["on_" + key]
                vis = ons[(ons >= self.vs) & (ons <= self.ve)]
                spacing = r.width() / max(1, vis.size)
                if key == "clap" or spacing >= 6:
                    sz = 5 if key == "clap" else 3.5
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(c.lighter(115) if key == "clap" else c.darker(130))
                    for t in vis:
                        x = self.x_of(t)
                        p.drawPolygon(QPolygonF([QPointF(x, cy - sz), QPointF(x + sz, cy), QPointF(x, cy + sz),
                                                 QPointF(x - sz, cy)]))
            p.restore()
            y += self.LANE_H
        p.end()
        # sóng màu "đã phát" (dán đè phía trái đầu phát)
        pm2 = self._pixmap()
        p2 = QPainter(pm2)
        p2.setClipRect(QRectF(r.left(), 0, r.width(), H))
        self._wave_lines(p2, self.played)
        p2.end()
        return pm, pm2

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        H = self.height()
        p.fillRect(self.rect(), QColor(T["wave_bg"]))
        r = self.wave_rect()
        if self.a is None or "peak" not in self.a:
            f = QFont("Segoe UI")
            f.setPixelSize(12)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor(T["text_faint"]))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.message)
            return
        key = self._static_key()
        if key != getattr(self, "_cache_key", None):
            self._cache = self._render_static()
            self._cache_key = key
        static, played = self._cache
        p.drawPixmap(0, 0, static)
        a = self.a
        xp = self.x_of(self.pos)
        if xp > r.left():                                     # phần đã phát: sóng màu đậm
            cut = min(r.right(), xp) - r.left()
            p.save()
            p.setClipRect(QRectF(r.left(), r.top(), cut, r.height()))
            p.drawPixmap(0, 0, played)
            p.restore()
        p.setClipRect(QRectF(r.left(), 0, r.width(), H))
        # IN / OUT, loop, vùng chọn, cue, Drop (vẽ mỗi khung — rất nhẹ)
        shade = QColor(T["wave_bg"])
        shade.setAlpha(170)
        end = self.end_ms or self.duration
        xs, xe = self.x_of(self.start_ms), self.x_of(end)
        if xs > r.left():
            p.fillRect(QRectF(r.left(), r.top(), xs - r.left(), r.height()), shade)
        if xe < r.right():
            p.fillRect(QRectF(xe, r.top(), r.right() - xe, r.height()), shade)
        for x, col in ((xs, T["ok"]), (xe, T["danger"])):
            if r.left() - 2 <= x <= r.right() + 2:
                p.setPen(QPen(QColor(col), 2))
                p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
        la, lb, lon = self.loop
        if lb > la:
            c = QColor("#a855f7")
            c.setAlpha(70 if lon else 30)
            p.fillRect(QRectF(self.x_of(la), r.top(), self.x_of(lb) - self.x_of(la), r.height()), c)
        if self.sel:
            c = QColor(T["accent"])
            c.setAlpha(60)
            x0, x1 = self.x_of(min(self.sel)), self.x_of(max(self.sel))
            p.fillRect(QRectF(x0, r.top(), x1 - x0, H - r.top()), c)
        for cm in self.cues:
            x = self.x_of(cm)
            p.setPen(QPen(QColor(T["ok"]), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
        if self.show["drops"]:
            red = QColor("#ef4444")
            for d in a["drops"]:
                if self.vs <= d <= self.ve:
                    x = self.x_of(d)
                    p.setPen(QPen(red, 1, Qt.PenStyle.DashLine))
                    p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(red)
                    p.drawPolygon(QPolygonF([QPointF(x - 7, r.top()), QPointF(x + 7, r.top()), QPointF(x, r.top() + 11)]))
        p.setClipping(False)
        y = self._lanes_bottom()
        if r.left() <= xp <= r.right():
            p.setPen(QPen(QColor("#ef4444"), 2))
            p.drawLine(QPointF(xp, self.SEC_H), QPointF(xp, y))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#ef4444"))
            p.drawPolygon(QPolygonF([QPointF(xp - 5, self.SEC_H + self.RULER_H - 6),
                                     QPointF(xp + 5, self.SEC_H + self.RULER_H - 6),
                                     QPointF(xp, self.SEC_H + self.RULER_H + 2)]))
        if self.hover is not None:
            p.setPen(QPen(QColor(T["text_dim"]), 1, Qt.PenStyle.DotLine))
            x = self.x_of(self.hover)
            p.drawLine(QPointF(x, r.top()), QPointF(x, y))

    # ---------- chuột
    def _lane_at(self, yy):
        y = self.wave_rect().bottom() + 6
        for key, *_ in LAYERS:
            if not self.show[key]:
                continue
            if y <= yy < y + self.LANE_H:
                return key
            y += self.LANE_H
        return None

    def mousePressEvent(self, e):
        if self.a is None or "peak" not in self.a:
            return
        x, y = e.position().x(), e.position().y()
        r = self.wave_rect()
        if x < r.left():
            return
        ms = max(0, min(self.duration, self.ms_of(x)))
        if e.button() == Qt.MouseButton.RightButton:
            self._rdrag = ms
            self.sel = None
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self.show["drops"] and r.top() - 2 <= y <= r.top() + 16:        # bấm điểm Drop -> đặt IN
            for d in self.a["drops"]:
                if abs(self.x_of(d) - x) <= 8:
                    self.dropClicked.emit(int(d))
                    return
        lane = self._lane_at(y)
        if lane:
            if lane == "vocal":
                for s, en in self.a["vocal"]:
                    if s - 50 <= ms <= en:
                        self.playRequested.emit(int(s))
                        return
            else:
                ons = self.a["on_" + lane]
                if ons.size:
                    i = int(np.argmin(np.abs(ons - ms)))
                    if abs(self.x_of(ons[i]) - x) <= 8:
                        self.playRequested.emit(int(ons[i]))
                        return
        self.seekRequested.emit(ms)

    def mouseMoveEvent(self, e):
        x = e.position().x()
        r = self.wave_rect()
        self.hover = max(0, min(self.duration, self.ms_of(x))) if x >= r.left() and self.a is not None else None
        if self._rdrag is not None and self.hover is not None:
            self.sel = (self._rdrag, self.hover)
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton and self._rdrag is not None:
            if self.sel and abs(self.sel[1] - self.sel[0]) < 50:
                self.sel = None
            self.selectionChanged.emit(self.sel)
            self._rdrag = None
            self.update()

    def leaveEvent(self, e):
        self.hover = None
        self.update()

    def wheelEvent(self, e):
        if self.a is None or "peak" not in self.a:
            return
        dy = e.angleDelta().y() or e.angleDelta().x()
        span = self.ve - self.vs
        if e.modifiers() & Qt.KeyboardModifier.ShiftModifier or e.angleDelta().x():
            sh = -span * 0.15 * (1 if dy > 0 else -1)
            self.set_view(self.vs + sh, self.ve + sh)
        else:
            c = self.ms_of(e.position().x())
            rel = (c - self.vs) / span if span else .5
            new = span * (0.8 if dy > 0 else 1.25)
            self.set_view(c - new * rel, c - new * rel + new)
        e.accept()


def dark_titlebar(widget):
    """Thanh tiêu đề Windows theo giao diện Tối / Sáng."""
    try:
        import ctypes
        import theme
        val = ctypes.c_int(1 if theme.is_dark() else 0)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(int(widget.winId()), attr, ctypes.byref(val), 4) == 0:
                break
    except Exception:
        pass


# ================================================================== cửa sổ Soi nhịp
class BeatScope(QWidget):
    def __init__(self, host, editor):
        super().__init__(None, Qt.WindowType.Window)
        self.host, self.ed = host, editor
        self.strip = None
        self.analyzer = None
        self._path = None
        self._syncing = False
        self.setWindowTitle("Soi nhịp")
        self.setObjectName("beatScope")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.resize(1500, 900)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 10)
        root.setSpacing(10)

        head = QHBoxLayout()
        self.lbl_title = QLabel("Soi nhịp")
        self.lbl_title.setObjectName("deTitle")
        head.addWidget(self.lbl_title)
        self.lbl_sub = QLabel("")
        self.lbl_sub.setObjectName("deSub")
        head.addWidget(self.lbl_sub)
        head.addStretch(1)
        self.lbl_bpm = QLabel("")
        self.lbl_bpm.setObjectName("deBpm")
        head.addWidget(self.lbl_bpm)
        head.addSpacing(16)
        self.lbl_time = QLabel("")
        self.lbl_time.setObjectName("deTime")
        head.addWidget(self.lbl_time)
        root.addLayout(head)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        self.chips = {}
        for key, name, col in LAYERS:
            self.chips[key] = self._chip(chips, key, name, col)
        sep = QFrame()
        sep.setObjectName("tbSep")
        sep.setFixedHeight(26)
        chips.addSpacing(6)
        chips.addWidget(sep)
        chips.addSpacing(6)
        for key, name, col in MARKS:
            self.chips[key] = self._chip(chips, key, name, col)
        chips.addStretch(1)
        root.addLayout(chips)

        ctl = QHBoxLayout()
        ctl.setSpacing(5)
        ed = self.ed
        self.b_play = None
        for text, fn, tip in (("⏮", ed.go_home, "Về điểm IN"), ("▶ / ‖", ed.play_pause, "Phát / tạm dừng"),
                              ("■", ed.stop, "Dừng")):
            b = self._btn(ctl, text, fn, tip)
            if text.startswith("▶"):
                self.b_play = b
        self._cap(ctl, "CUE")
        self._btn(ctl, "+ Cue", lambda: (ed.add_cue(), self.sync()), "Thêm Hot Cue tại vị trí hiện tại")
        self._cap(ctl, "CẮT")
        self._btn(ctl, "IN", lambda: (ed.set_in(), self.sync()), "Đặt IN tại vị trí hiện tại")
        self._btn(ctl, "OUT", lambda: (ed.set_out(), self.sync()), "Đặt OUT tại vị trí hiện tại")
        self._btn(ctl, "✕", lambda: (ed.clear_in_out(), self.sync()), "Bỏ cắt")
        self._cap(ctl, "LOOP")
        self._btn(ctl, "A", lambda: (ed.set_a(), self.sync()), "Đặt A")
        self._btn(ctl, "B", lambda: (ed.set_b(), self.sync()), "Đặt B và bật lặp")
        self._btn(ctl, "⟳", lambda: (ed.b_loop.click(), self.sync()), "Bật / tắt lặp A-B")
        for sec in (1, 2, 4, 8):
            self._btn(ctl, f"{sec}s", lambda _c=False, s=sec: (ed.loop_len(s), self.sync()), f"Lặp {sec} giây")
        self._btn(ctl, "Loop vùng chọn", self.loop_sel, "Lặp vùng đã chọn (chuột phải kéo trên sóng)")
        self._btn(ctl, "✕", lambda: (ed.clear_loop(), self.sync()), "Bỏ vùng lặp")
        ctl.addStretch(1)
        self._btn(ctl, "Toàn bài", lambda: self.view.set_view(0, self.view.duration), "Xem cả bài")
        root.addLayout(ctl)

        hc = QHBoxLayout()
        hc.setSpacing(6)
        cap = QLabel("HOT CUE")
        cap.setObjectName("deCap")
        hc.addWidget(cap)
        self.hot_row = QHBoxLayout()
        self.hot_row.setSpacing(6)
        hc.addLayout(self.hot_row)
        hc.addStretch(1)
        root.addLayout(hc)

        self.view = BeatView()
        self.view.seekRequested.connect(lambda ms: (self.ed.seek(ms), self.sync()))
        self.view.playRequested.connect(self.seek_play)
        self.view.dropClicked.connect(self.drop_in)
        self.view.selectionChanged.connect(self.on_sel)
        root.addWidget(self.view, 1)

        hint = QLabel("<b>Bấm sóng</b> = tua · <b>Chuột phải kéo</b> = chọn vùng · <b>Lăn chuột</b> = phóng to tại con trỏ "
                      "(Shift = kéo ngang) · <b>Bấm tam giác Drop</b> = đặt IN · <b>Bấm điểm nhạc cụ</b> = tua &amp; phát · "
                      "<b>Bấm Hot Cue</b> = nhảy &amp; phát")
        hint.setObjectName("deHint")
        hint.setWordWrap(True)
        root.addWidget(hint)
        note = QLabel("Nhận diện nhạc cụ theo dải tần và nhịp gõ (không tách nhạc bằng AI): Clap và Giọng hát là ước lượng.")
        note.setObjectName("deHint")
        root.addWidget(note)

        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.tick)

    # ---------- dựng
    def _chip(self, lay, key, name, col):
        b = QPushButton(name)
        b.setCheckable(True)
        b.setChecked(True)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.setProperty("col", col)
        b.setProperty("name", name)
        b.toggled.connect(lambda on, k=key: self.toggle_layer(k, on))
        self._chip_style(b, True)
        lay.addWidget(b)
        return b

    def _chip_style(self, b, on):
        col = b.property("col")
        c = QColor(col)
        txt = "#111" if c.lightness() > 140 else "white"
        if on:
            b.setStyleSheet(f"QPushButton{{background:{col};color:{txt};border:none;border-radius:16px;"
                            f"padding:6px 16px;font-weight:700;font-size:10pt;}}")
        else:
            b.setStyleSheet(f"QPushButton{{background:transparent;color:{col};border:1.5px solid {col};"
                            f"border-radius:16px;padding:5px 15px;font-weight:700;font-size:10pt;}}")

    def _btn(self, lay, text, fn, tip):
        b = QPushButton(text)
        b.setObjectName("deBtn")
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.setToolTip(tip)
        b.clicked.connect(fn)
        lay.addWidget(b)
        return b

    def _cap(self, lay, text):
        lay.addSpacing(8)
        lb = QLabel(text)
        lb.setObjectName("deCap")
        lay.addWidget(lb)

    # ---------- dữ liệu
    def set_strip(self, strip):
        self.strip = strip
        path = strip.path if strip else ""
        if path != self._path:
            self._path = path
            if self.analyzer:
                self.analyzer.stop()
                self.analyzer = None
            self.view.set_analysis(None)
            self.view.message = "Kênh trống" if not path else "Đang phân tích bài..."
            for key, *_ in LAYERS:
                self.chips[key].setText(self.chips[key].property("name"))
            if path:
                self.analyzer = BeatAnalyzer(path, self)
                self.analyzer.progress.connect(self.on_progress)
                self.analyzer.done.connect(lambda r, p=path: self.on_done(p, r))
                self.analyzer.start()
        self.sync()

    def on_progress(self, pc, msg):
        self.view.message = f"{msg}  {pc}%"
        self.view.update()

    def on_done(self, path, r):
        if not self.strip or self.strip.path != path:
            return
        if not r or "error" in r:
            self.view.message = "Không phân tích được bài này" + (f": {r['error']}" if r and "error" in r else "")
            self.view.update()
            return
        self.view.set_analysis(r)
        for key, name, _c in LAYERS:
            n = len(r["vocal"]) if key == "vocal" else int(r["on_" + key].size)
            self.chips[key].setText(f"{name}   {n}")
        # dùng nhịp phân tích được cho lưới nhịp của bảng chỉnh bài
        bpm = float(r["bpm"])
        if bpm > 0 and r["beats"].size:
            self.strip.bpm_auto = bpm
            self.strip.bpm_off = int(r["beats"][0])
            self.ed.refresh()
        self.sync()

    def sync(self):
        s = self.strip
        v = self.view
        if s:
            v.start_ms, v.end_ms = s.start_ms, s.end_ms
            v.cues = list(s.cues)
            v.loop = (s.loop_a, s.loop_b, s.ab_on)
            v.played = QColor(channel_dot(s.color) if s.color else "#f59e0b")
            self.lbl_title.setText(s.display_name() if s.path else f"Kênh {s.number} (trống)")
            self.lbl_sub.setText(f"Kênh {s.number}")
            bpm = s.bpm or s.bpm_auto
            self.lbl_bpm.setText(f"BPM {bpm:.0f}" if bpm else "")
        self.rebuild_hot()
        self.tick()

    def sync_light(self):
        """Đồng bộ khi bảng chỉnh bài thay đổi (không gọi ngược lại bảng chỉnh bài)."""
        if not self._syncing:
            self._syncing = True
            try:
                self.sync()
            finally:
                self._syncing = False

    def rebuild_hot(self):
        while self.hot_row.count():
            it = self.hot_row.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        cues = self.strip.cues if self.strip else []
        if not cues:
            lb = QLabel('Chưa có Hot Cue — bấm "+ Cue" để đánh dấu điểm nhớ; bấm pad để nhảy & phát.')
            lb.setObjectName("deHint")
            self.hot_row.addWidget(lb)
            return
        cols = ["#22c55e", "#f59e0b", "#38bdf8", "#e879f9", "#ef4444", "#a78bfa", "#fb7185", "#14b8a6", "#eab308"]
        for i, ms in enumerate(cues):
            from deck_editor import tfmt
            b = QPushButton(f"{i + 1}   {tfmt(ms)}")
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            c = cols[i % len(cols)]
            b.setStyleSheet(f"QPushButton{{background:{c};color:#111;border:none;border-radius:8px;padding:6px 14px;"
                            f"font-family:Consolas;font-weight:700;}} QPushButton:hover{{background:{QColor(c).lighter(115).name()};}}")
            b.setToolTip("Bấm: nhảy tới và phát · Chuột phải: xóa")
            b.clicked.connect(lambda _c=False, ms=ms: self.seek_play(ms))
            b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda _p, i=i: (self.ed.remove_cue(i), self.sync()))
            self.hot_row.addWidget(b)

    # ---------- thao tác
    def toggle_layer(self, key, on):
        self._chip_style(self.chips[key], on)
        self.view.show[key] = on
        self.view.update()

    def seek_play(self, ms):
        self.ed.seek(ms)
        if not self.ed.active() or (self.strip and self.strip.deck.is_paused()):
            self.ed.play_pause()
        self.sync()

    def drop_in(self, ms):
        s = self.strip
        if s:
            self.ed.set_in_out(min(ms, (s.end_ms or self.view.duration) - 100), s.end_ms)
            self.host.statusBar().showMessage(f"Đã đặt IN tại điểm Drop {ms / 1000:.1f} s", 3000)
            self.sync()

    def on_sel(self, sel):
        self.ed.wave.sel = sel
        self.ed.wave.update()

    def loop_sel(self):
        if self.view.sel:
            self.ed.wave.sel = self.view.sel
        self.ed.loop_selection()
        self.view.sel = None
        self.sync()

    def tick(self):
        s = self.strip
        if not s or not self.isVisible():
            return
        pos = self.ed.cur() if self.ed.strip is s else 0
        self.view.pos = pos
        dur = self.view.duration
        from deck_editor import tfmt
        self.lbl_time.setText(f"{tfmt(pos)}  /  {tfmt(dur)}" if s.path else "")
        v = self.view
        if s.deck.is_playing() and (pos > v.ve or pos < v.vs) and v.ve - v.vs < v.duration:
            span = v.ve - v.vs
            v.set_view(pos - span * 0.1, pos + span * 0.9)
        v.update()

    def showEvent(self, e):
        self.timer.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def closeEvent(self, e):
        self.timer.stop()
        super().closeEvent(e)
