import ctypes as C
from enum import IntEnum

MAGIC = 0x50414345
VERSION = 1
MAX_DOF = 8
MAX_POINTS = 256
MAX_PARAMS = 16
TOOL_POSE_DIM = 7


class MsgType(IntEnum):
    NONE = 0; PATH = 1; PATH_S = 2; CORRECTION = 3; PARAM = 4; EVENT = 5; CONTRACT = 6


class Space(IntEnum):
    JOINT = 0; TOOL = 1


class Supplier(IntEnum):
    UNKNOWN = 0; AI = 1; LOCAL = 2; EYE = 3; RULE = 4; TEACH = 5; OPERATOR = 6; CONTROL = 7


class EventCode(IntEnum):
    NONE = 0; SEAM_END = 1; PAUSE = 2; RESUME = 3; DEFECT = 4; ESTOP = 5


class Header(C.Structure):
    _fields_ = [
        ("magic", C.c_uint32), ("version", C.c_uint16), ("type", C.c_uint16),
        ("seq", C.c_uint64), ("t_gen_ns", C.c_uint64), ("t_valid_until_ns", C.c_uint64),
        ("confidence", C.c_float), ("supplier", C.c_uint16), ("space", C.c_uint16),
        ("dof", C.c_uint16), ("n_points", C.c_uint16), ("flags", C.c_uint32),
        ("_pad", C.c_uint8 * 16),
    ]


class Path(C.Structure):
    _fields_ = [("t0_ns", C.c_uint64), ("dt_ns", C.c_uint64), ("pts", (C.c_float * MAX_DOF) * MAX_POINTS)]


class PathS(C.Structure):
    _fields_ = [("s0", C.c_float), ("s1", C.c_float), ("ref_id", C.c_uint32), ("sdot_nominal", C.c_float),
                ("pts", (C.c_float * MAX_DOF) * MAX_POINTS)]


class Correction(C.Structure):
    _fields_ = [("s0", C.c_float), ("ds", C.c_float), ("t0_ns", C.c_uint64), ("dt_ns", C.c_uint64),
                ("ref_id", C.c_uint32), ("by_time", C.c_uint32), ("pts", (C.c_float * 4) * MAX_POINTS)]


class Param(C.Structure):
    _fields_ = [("speed_scale", C.c_float), ("n_params", C.c_uint32), ("params", C.c_float * MAX_PARAMS)]


class Event(C.Structure):
    _fields_ = [("code", C.c_uint32), ("arg", C.c_uint32)]


class Contract(C.Structure):
    _fields_ = [("buffer_margin_ns", C.c_int64), ("next_deadline_ns", C.c_uint64),
                ("latency_p50_ns", C.c_uint64), ("latency_p95_ns", C.c_uint64), ("latency_p99_ns", C.c_uint64),
                ("progress_s", C.c_float), ("speed_scale", C.c_float),
                # 실행 상태 (C pace_contract_t 와 같은 순서·크기 = 72 B): 온라인 학습 라벨 거름망용
                ("t_ns", C.c_uint64), ("mode", C.c_uint16), ("supplier", C.c_uint16), ("monitor", C.c_uint16), ("stop_level", C.c_uint16),
                ("n_reject", C.c_uint32), ("n_unclean", C.c_uint32)]


assert C.sizeof(Contract) == 72, "Contract 미러 크기가 C pace_contract_t(72 B)와 다름"


class Body(C.Union):
    _fields_ = [("path", Path), ("path_s", PathS), ("correction", Correction), ("param", Param),
                ("event", Event), ("contract", Contract)]


class Msg(C.Structure):
    _fields_ = [("hdr", Header), ("body", Body)]

    def init(self, mtype, supplier, seq, t_gen_ns, t_valid_until_ns, confidence):
        C.memset(C.addressof(self), 0, C.sizeof(self))
        h = self.hdr
        h.magic, h.version, h.type = MAGIC, VERSION, int(mtype)
        h.seq, h.t_gen_ns, h.t_valid_until_ns = seq, t_gen_ns, t_valid_until_ns
        h.confidence, h.supplier = float(confidence), int(supplier)
        return self

    def valid_header(self):
        h = self.hdr
        return (h.magic == MAGIC and h.version == VERSION and MsgType.PATH <= h.type <= MsgType.CONTRACT
                and h.n_points <= MAX_POINTS and h.dof <= MAX_DOF and 0.0 <= h.confidence <= 1.0)

    def expired(self, now_ns):
        return now_ns > self.hdr.t_valid_until_ns


# ---- 상태 구조체 (pace/state.h) ----
ST_COUNT = 10


class RobotState(C.Structure):
    _fields_ = [("t_ns", C.c_uint64), ("dof", C.c_uint16), ("valid", C.c_uint16), ("hal_fault", C.c_uint32),
                ("q", C.c_float * MAX_DOF), ("qd", C.c_float * MAX_DOF), ("qdd", C.c_float * MAX_DOF),
                ("tau", C.c_float * MAX_DOF), ("tool_pose", C.c_float * TOOL_POSE_DIM), ("tool_force", C.c_float)]


class HalLimits(C.Structure):
    _fields_ = [("dof", C.c_uint16), ("accepts_position", C.c_uint16), ("accepts_velocity", C.c_uint16),
                ("accepts_effort", C.c_uint16), ("native_period_ns", C.c_uint32), ("read_wcet_ns", C.c_uint32),
                ("write_wcet_ns", C.c_uint32),
                ("q_min", C.c_float * MAX_DOF), ("q_max", C.c_float * MAX_DOF), ("qd_max", C.c_float * MAX_DOF),
                ("qdd_max", C.c_float * MAX_DOF), ("jerk_max", C.c_float * MAX_DOF), ("tau_max", C.c_float * MAX_DOF),
                ("workspace_min", C.c_float * 3), ("workspace_max", C.c_float * 3)]


class Mode(IntEnum):
    INIT = 0; NORMAL = 1; PACING = 2; LOCAL = 3; EXTRAP = 4; HOLD = 5; STOPPED = 6; RECOVER = 7


class TickRecord(C.Structure):
    _fields_ = [("tick", C.c_uint64), ("t_sched_ns", C.c_uint64), ("t_wake_ns", C.c_uint64),
                ("stage_ns", C.c_uint32 * ST_COUNT), ("chunk_seq", C.c_uint64), ("chunk_t_gen_ns", C.c_uint64),
                ("progress_s", C.c_float), ("deviation", C.c_float), ("speed_scale", C.c_float),
                ("buffer_margin_ms", C.c_float), ("mode", C.c_uint16), ("supplier", C.c_uint16),
                ("reject", C.c_uint16), ("monitor", C.c_uint16), ("triggers", C.c_uint32), ("stop_level", C.c_uint16), ("arc_on", C.c_uint16), ("arc_power_pct", C.c_uint16), ("tool_force_cN", C.c_uint16), ("_pad", C.c_uint8 * 12)]


assert C.sizeof(Header) == 64, C.sizeof(Header)
assert C.sizeof(Msg) == 64 + C.sizeof(Path), C.sizeof(Msg)
assert C.sizeof(TickRecord) == 128, C.sizeof(TickRecord)
