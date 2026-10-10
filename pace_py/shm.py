"""공유메모리 접근 (pace/shm.h 미러). 비실시간 Python 프로세스용.

원자성에 대한 주의: Python 에서는 C11 atomics 를 쓸 수 없다. x86-64 의 TSO 메모리 모델에서는
정렬된 8바이트 store/load 가 원자적이고 store-store, load-load 순서가 유지되므로,
"데이터 memmove → head 기록" 순서를 지키면 SPSC 생산자로 안전하다. 소비자 쪽도 같은 논리.
ARM 등 약한 메모리 모델에서는 C 바인딩(libpace)을 거쳐야 한다. 이 모듈은 x86-64 전용으로 둔다.
"""
import ctypes as C
import mmap
import os
import platform
import time

from .msg import Msg, RobotState, HalLimits, Contract, TickRecord

assert platform.machine() in ("x86_64", "AMD64"), "pace_py.shm: x86-64 전용 (TSO 가정)"

CACHELINE = 64
NQUEUES = 4
Q_AI, Q_LOCAL, Q_EYE, Q_OPERATOR = 0, 1, 2, 3
FRAME_MAX_W, FRAME_MAX_H, FRAME_MAX_C = 640, 480, 3
FRAME_MAX_BYTES = FRAME_MAX_W * FRAME_MAX_H * FRAME_MAX_C


def now_ns():
    return time.monotonic_ns()


class ShmHeader(C.Structure):
    _fields_ = [("magic", C.c_uint32), ("version", C.c_uint32), ("total_bytes", C.c_uint64), ("created_ns", C.c_uint64),
                ("off_queue", C.c_uint64 * NQUEUES), ("off_state", C.c_uint64), ("off_contract", C.c_uint64),
                ("off_limits", C.c_uint64), ("off_metrics", C.c_uint64), ("off_frame", C.c_uint64),
                ("queue_cap", C.c_uint32), ("metrics_cap", C.c_uint32), ("msg_size", C.c_uint32),
                ("record_size", C.c_uint32), ("_pad", C.c_uint8 * (CACHELINE * 2 - 112))]


class Spsc(C.Structure):
    _fields_ = [("head", C.c_uint64), ("_p0", C.c_uint8 * 56), ("tail", C.c_uint64), ("_p1", C.c_uint8 * 56),
                ("capacity", C.c_uint32), ("elem_size", C.c_uint32), ("mask", C.c_uint64), ("drops", C.c_uint64),
                ("_p2", C.c_uint8 * (CACHELINE - 24))]


class Seqlock(C.Structure):
    _fields_ = [("seq", C.c_uint64), ("data_size", C.c_uint32), ("_p0", C.c_uint32), ("writes", C.c_uint64),
                ("_p1", C.c_uint8 * (CACHELINE - 8 - 16))]


class Frame(C.Structure):
    _fields_ = [("t_ns", C.c_uint64), ("seq", C.c_uint64), ("width", C.c_uint32), ("height", C.c_uint32),
                ("channels", C.c_uint32), ("camera_id", C.c_uint32), ("data", C.c_uint8 * FRAME_MAX_BYTES)]


assert C.sizeof(ShmHeader) == 128 and C.sizeof(Spsc) == 192 and C.sizeof(Seqlock) == 64


class Shm:
    """이미 C 쪽(pace_shm_create)이 만든 영역을 연다. Python 은 생성하지 않는다."""

    def __init__(self, name: str):
        path = f"/dev/shm/{name.lstrip('/')}"
        self.fd = os.open(path, os.O_RDWR)
        size = os.fstat(self.fd).st_size
        self.mm = mmap.mmap(self.fd, size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
        self.buf = (C.c_uint8 * size).from_buffer(self.mm)
        self.base = C.addressof(self.buf)
        self.hdr = ShmHeader.from_buffer(self.mm, 0)
        if self.hdr.magic != 0x50534D31 or self.hdr.version != 1 or self.hdr.total_bytes != size:
            raise RuntimeError("pace shm header mismatch")
        if self.hdr.msg_size != C.sizeof(Msg) or self.hdr.record_size != C.sizeof(TickRecord):
            raise RuntimeError("pace shm struct size mismatch (C/Python 레이아웃 불일치)")

    def close(self):
        del self.buf; del self.hdr
        self.mm.close(); os.close(self.fd)

    # ---- SPSC ----
    def _q(self, off): return Spsc.from_buffer(self.mm, off)

    def _spsc_push(self, off, obj):
        q = self._q(off); size = C.sizeof(obj)
        head, tail = q.head, q.tail
        if head - tail >= q.capacity:
            q.drops += 1; return False
        slot = off + C.sizeof(Spsc) + (head & q.mask) * q.elem_size
        C.memmove(self.base + slot, C.addressof(obj), size)
        q.head = head + 1          # x86 TSO: 데이터 store 뒤에 head store
        return True

    def _spsc_pop(self, off, obj):
        q = self._q(off)
        tail, head = q.tail, q.head
        if head == tail: return False
        slot = off + C.sizeof(Spsc) + (tail & q.mask) * q.elem_size
        C.memmove(C.addressof(obj), self.base + slot, C.sizeof(obj))
        q.tail = tail + 1
        return True

    def _spsc_count(self, off):
        q = self._q(off); return q.head - q.tail

    def push_msg(self, qid: int, m: Msg) -> bool: return self._spsc_push(self.hdr.off_queue[qid], m)
    def pop_msg(self, qid: int, m: Msg) -> bool: return self._spsc_pop(self.hdr.off_queue[qid], m)
    def queue_count(self, qid: int) -> int: return self._spsc_count(self.hdr.off_queue[qid])
    def pop_record(self, r: TickRecord) -> bool: return self._spsc_pop(self.hdr.off_metrics, r)
    def metrics_count(self) -> int: return self._spsc_count(self.hdr.off_metrics)

    # ---- seqlock ----
    def _seq_read(self, off, obj, max_retry=1024):
        s = Seqlock.from_buffer(self.mm, off)
        for _ in range(max_retry + 1):
            s1 = s.seq
            if s1 == 0: return False
            if s1 & 1: continue
            C.memmove(C.addressof(obj), self.base + off + C.sizeof(Seqlock), s.data_size)
            if s.seq == s1: return True
        return False

    def _seq_write(self, off, obj):
        s = Seqlock.from_buffer(self.mm, off)
        v = s.seq; s.seq = v + 1
        C.memmove(self.base + off + C.sizeof(Seqlock), C.addressof(obj), s.data_size)
        s.writes += 1; s.seq = v + 2

    def read_state(self, st: RobotState) -> bool: return self._seq_read(self.hdr.off_state, st)
    def read_contract(self, c: Contract) -> bool: return self._seq_read(self.hdr.off_contract, c)
    def read_limits(self, l: HalLimits) -> bool: return self._seq_read(self.hdr.off_limits, l)
    def read_frame(self, f: Frame) -> bool: return self._seq_read(self.hdr.off_frame, f)
    def write_frame(self, f: Frame): self._seq_write(self.hdr.off_frame, f)
    # 테스트·시뮬용 (실시간 루프가 없을 때 Python 이 상태를 쓰는 경우)
    def write_state(self, st: RobotState): self._seq_write(self.hdr.off_state, st)
    def write_limits(self, l: HalLimits): self._seq_write(self.hdr.off_limits, l)
