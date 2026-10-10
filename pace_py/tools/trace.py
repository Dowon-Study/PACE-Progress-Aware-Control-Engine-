"""pace_control --trace 가 쓰는 바이너리 trace 로더 (헤더: u64 n, u32 dof, u32 record_size; 레코드: trace_t)."""
import numpy as np

def load_trace(path):
    with open(path, "rb") as f:
        n = int(np.frombuffer(f.read(8), np.uint64)[0]); dof, sz = np.frombuffer(f.read(8), np.uint32)
        dt = np.dtype({"names": ["t_ns", "q_cmd", "q_meas", "tool", "speed", "mode", "monitor"],
                       "formats": ["<u8", ("<f4", 8), ("<f4", 8), ("<f4", 7), "<f4", "<u2", "<u2"], "itemsize": int(sz)})
        a = np.frombuffer(f.read(n * int(sz)), dt, count=n)
    valid = a["t_ns"] > 0
    return {"t_ns": a["t_ns"][valid], "q_cmd": a["q_cmd"][valid][:, :dof], "q_meas": a["q_meas"][valid][:, :dof], "tool": a["tool"][valid],
            "speed": a["speed"][valid], "mode": a["mode"][valid], "monitor": a["monitor"][valid], "dof": int(dof)}
