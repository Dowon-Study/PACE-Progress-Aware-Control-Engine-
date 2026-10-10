"""C 레이아웃과 Python ctypes 미러의 바이트 단위 일치, 그리고 C↔Python 공유메모리 왕복."""
import ctypes as C
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
BUILD = ROOT / "pace" / "build"

from pace_py import msg as M            # noqa: E402
from pace_py import shm as S            # noqa: E402


def c_layout():
    out = subprocess.check_output([str(BUILD / "test_layout")], text=True)
    return json.loads(out)


def test_sizes_match_c():
    L = c_layout()
    assert L["msg"] == C.sizeof(M.Msg)
    assert L["header"] == C.sizeof(M.Header)
    assert L["path"] == C.sizeof(M.Path) and L["path_s"] == C.sizeof(M.PathS)
    assert L["correction"] == C.sizeof(M.Correction) and L["param"] == C.sizeof(M.Param)
    assert L["event"] == C.sizeof(M.Event) and L["contract"] == C.sizeof(M.Contract)
    assert L["state"] == C.sizeof(M.RobotState) and L["limits"] == C.sizeof(M.HalLimits)
    assert L["record"] == C.sizeof(M.TickRecord) and L["frame"] == C.sizeof(S.Frame)
    assert L["spsc"] == C.sizeof(S.Spsc) and L["seqlock"] == C.sizeof(S.Seqlock)
    assert L["shm_header"] == C.sizeof(S.ShmHeader)


def test_offsets_match_c():
    L = c_layout()["off"]
    assert L["hdr_seq"] == M.Header.seq.offset and L["hdr_t_gen"] == M.Header.t_gen_ns.offset
    assert L["hdr_conf"] == M.Header.confidence.offset and L["hdr_supplier"] == M.Header.supplier.offset
    assert L["hdr_n_points"] == M.Header.n_points.offset and L["body"] == M.Msg.body.offset
    assert L["path_pts"] == M.Path.pts.offset and L["path_s_pts"] == M.PathS.pts.offset
    assert L["corr_pts"] == M.Correction.pts.offset and L["param_params"] == M.Param.params.offset
    assert L["rec_stage"] == M.TickRecord.stage_ns.offset and L["rec_progress"] == M.TickRecord.progress_s.offset
    assert L["rec_mode"] == M.TickRecord.mode.offset and L["rec_triggers"] == M.TickRecord.triggers.offset
    assert L["spsc_tail"] == S.Spsc.tail.offset and L["spsc_capacity"] == S.Spsc.capacity.offset
    assert L["spsc_mask"] == S.Spsc.mask.offset and L["seqlock_data_size"] == S.Seqlock.data_size.offset
    assert L["frame_data"] == S.Frame.data.offset


def test_c_python_roundtrip():
    """C 가 영역을 만들고, Python 이 메시지를 넣고 상태를 쓰고, C 가 꺼내서 확인한다 (pace_shm_tool)."""
    tool = BUILD / "pace_shm_tool"
    name = "/pace_pytest_shm"
    subprocess.check_call([str(tool), "create", name])
    try:
        sh = S.Shm(name)
        m = M.Msg().init(M.MsgType.PATH, M.Supplier.AI, 7, 1_000_000, 500_000_000, 0.75)
        m.hdr.space, m.hdr.dof, m.hdr.n_points = M.Space.TOOL, 7, 4
        m.body.path.t0_ns, m.body.path.dt_ns = 2_000_000, 20_000_000
        for i in range(4):
            for d in range(7):
                m.body.path.pts[i][d] = i + d / 10.0
        assert m.valid_header() and sh.push_msg(S.Q_AI, m) and sh.queue_count(S.Q_AI) == 1
        p = M.Msg().init(M.MsgType.PARAM, M.Supplier.OPERATOR, 1, 0, 10**12, 1.0)
        p.body.param.speed_scale = 0.6
        assert sh.push_msg(S.Q_OPERATOR, p)
        st = M.RobotState(); st.t_ns = 4242; st.dof = 6; st.q[2] = 0.25
        sh.write_state(st)
        out = subprocess.check_output([str(tool), "dump", name], text=True)
        d = json.loads(out)
        assert d["ai"]["seq"] == 7 and d["ai"]["type"] == 1 and abs(d["ai"]["pt3_6"] - 3.6) < 1e-6
        assert d["ai"]["t0_ns"] == 2_000_000 and d["operator"]["speed_scale"] == 0.6
        assert d["state"]["t_ns"] == 4242 and abs(d["state"]["q2"] - 0.25) < 1e-6
        # C 가 꺼낸 뒤에는 비어 있어야 함
        assert sh.queue_count(S.Q_AI) == 0
        sh.close()
    finally:
        subprocess.call([str(tool), "unlink", name])
