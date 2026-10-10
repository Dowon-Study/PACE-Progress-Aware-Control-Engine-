/* 공유메모리 CLI: create <name> | dump <name> | unlink <name> | info
 * dump: 각 큐에서 메시지 하나씩 꺼내고 상태를 읽어 JSON 으로 출력 (Python 왕복 테스트용) */
#include <stdio.h>
#include <string.h>
#include "pace/shm.h"

static void dump_msg(const char *key, pace_shm_t *h, pace_queue_id_t q)
{
    pace_msg_t m;
    if (!pace_shm_pop_msg(h, q, &m)) { printf("\"%s\":null", key); return; }
    printf("\"%s\":{\"type\":%u,\"seq\":%llu,\"supplier\":%u,\"conf\":%.4f,\"n_points\":%u,\"dof\":%u", key,
           m.hdr.type, (unsigned long long)m.hdr.seq, m.hdr.supplier, m.hdr.confidence, m.hdr.n_points, m.hdr.dof);
    if (m.hdr.type == PACE_MSG_PATH)
        printf(",\"t0_ns\":%llu,\"dt_ns\":%llu,\"pt3_6\":%.6f", (unsigned long long)m.body.path.t0_ns, (unsigned long long)m.body.path.dt_ns, m.body.path.pts[3][6]);
    if (m.hdr.type == PACE_MSG_PATH_S)
        printf(",\"s0\":%.6f,\"s1\":%.6f", m.body.path_s.s0, m.body.path_s.s1);
    if (m.hdr.type == PACE_MSG_PARAM)
        printf(",\"speed_scale\":%.4f", m.body.param.speed_scale);
    if (m.hdr.type == PACE_MSG_EVENT)
        printf(",\"code\":%u", m.body.event.code);
    printf("}");
}

int main(int argc, char **argv)
{
    if (argc < 2) { fprintf(stderr, "usage: %s create|dump|unlink <name> | info\n", argv[0]); return 2; }
    if (!strcmp(argv[1], "info")) { printf("{\"total_bytes\":%zu,\"msg\":%zu,\"record\":%zu}\n", pace_shm_total_bytes(), sizeof(pace_msg_t), sizeof(pace_tick_record_t)); return 0; }
    if (argc < 3) return 2;
    const char *name = argv[2];
    pace_shm_t h;
    if (!strcmp(argv[1], "create")) { int r = pace_shm_create(name, &h); if (r) { fprintf(stderr, "create failed %d\n", r); return 1; } pace_shm_close(&h); return 0; }
    if (!strcmp(argv[1], "unlink")) return pace_shm_unlink(name) ? 1 : 0;
    if (!strcmp(argv[1], "dump")) {
        int r = pace_shm_open(name, &h); if (r) { fprintf(stderr, "open failed %d\n", r); return 1; }
        printf("{"); dump_msg("ai", &h, PACE_Q_AI); printf(","); dump_msg("local", &h, PACE_Q_LOCAL); printf(",");
        dump_msg("eye", &h, PACE_Q_EYE); printf(","); dump_msg("operator", &h, PACE_Q_OPERATOR);
        pace_robot_state_t st;
        if (pace_shm_read_state(&h, &st)) printf(",\"state\":{\"t_ns\":%llu,\"dof\":%u,\"q2\":%.6f}", (unsigned long long)st.t_ns, st.dof, st.q[2]);
        else printf(",\"state\":null");
        printf(",\"metrics_count\":%llu}\n", (unsigned long long)pace_spsc_count(h.metrics));
        pace_shm_close(&h); return 0;
    }
    return 2;
}
