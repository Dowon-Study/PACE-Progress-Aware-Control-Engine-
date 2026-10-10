/*
 * 공유메모리 레이아웃 (docs/IDEA_FIXED.md 3절·5절의 "락프리 공유메모리")
 *
 *  영역                         구조        작성자                 독자
 *  ─────────────────────────────────────────────────────────────────────────────
 *  q[AI]        청크 큐          SPSC        AI 추론 프로세스        1kHz 루프
 *  q[LOCAL]     청크 큐          SPSC        로컬 연속 정책          1kHz 루프
 *  q[EYE]       보정 큐          SPSC        작은 눈                 1kHz 루프
 *  q[OPERATOR]  PARAM/EVENT 큐   SPSC        운영자/장애 주입기      1kHz 루프
 *  state        로봇 상태        seqlock     1kHz 루프               AI, 로컬, 측정
 *  contract     시간 계약        seqlock     1kHz 루프               AI, 로컬
 *  metrics      틱 레코드 링     SPSC        1kHz 루프               측정 프로세스
 *  frame        카메라 프레임    seqlock     시뮬 렌더 스레드        AI, 로컬, 작은 눈
 *
 *  공급자별로 큐를 하나씩 두는 이유: SPSC 는 생산자가 하나여야 한다. 한 큐가 모든 메시지 종류를 나른다.
 *  전부 고정 크기, 생성 시 mlock + 사전 터치. 레이아웃은 pace_py/shm.py 와 일치해야 한다.
 */
#ifndef PACE_SHM_H
#define PACE_SHM_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include "pace/msg.h"
#include "pace/state.h"
#include "pace/spsc.h"
#include "pace/seqlock.h"

#ifdef __cplusplus
extern "C" {
#endif

#define PACE_SHM_MAGIC        0x50534D31u   /* 'PSM1' */
#define PACE_SHM_VERSION      1u
#define PACE_SHM_NQUEUES      4u
#define PACE_SHM_QUEUE_CAP    16u           /* 메시지 큐 깊이 */
#define PACE_SHM_METRICS_CAP  65536u        /* 틱 레코드 65536 = 65초 분량 */
#define PACE_FRAME_MAX_W      640u
#define PACE_FRAME_MAX_H      480u
#define PACE_FRAME_MAX_C      3u
#define PACE_FRAME_MAX_BYTES  (PACE_FRAME_MAX_W * PACE_FRAME_MAX_H * PACE_FRAME_MAX_C)

/* 큐 인덱스 */
typedef enum { PACE_Q_AI = 0, PACE_Q_LOCAL = 1, PACE_Q_EYE = 2, PACE_Q_OPERATOR = 3 } pace_queue_id_t;

/* 카메라 프레임 (seqlock 데이터) */
typedef struct {
    uint64_t t_ns;              /* 촬영(렌더) 시각 */
    uint64_t seq;
    uint32_t width, height, channels;
    uint32_t camera_id;
    uint8_t  data[PACE_FRAME_MAX_BYTES];
} pace_frame_t;

/* 공유메모리 맨 앞 헤더 (오프셋 테이블) */
typedef struct {
    uint32_t magic;
    uint32_t version;
    uint64_t total_bytes;
    uint64_t created_ns;
    uint64_t off_queue[PACE_SHM_NQUEUES];
    uint64_t off_state;
    uint64_t off_contract;
    uint64_t off_limits;
    uint64_t off_metrics;
    uint64_t off_frame;
    uint32_t queue_cap;
    uint32_t metrics_cap;
    uint32_t msg_size;
    uint32_t record_size;
    uint8_t  _pad[PACE_CACHELINE * 2 - 112];
} pace_shm_header_t;

_Static_assert(sizeof(pace_shm_header_t) == PACE_CACHELINE * 2, "pace_shm_header_t layout");

/* 프로세스 로컬 핸들 (공유메모리에 들어가지 않음) */
typedef struct {
    int fd;
    void *base;
    size_t size;
    char name[64];
    pace_shm_header_t *hdr;
    pace_spsc_t *queue[PACE_SHM_NQUEUES];
    pace_seqlock_t *state;
    pace_seqlock_t *contract;
    pace_seqlock_t *limits;
    pace_spsc_t *metrics;
    pace_seqlock_t *frame;
} pace_shm_t;

size_t pace_shm_total_bytes(void);

/* 생성(기존 것은 덮어씀) + mlock + 사전 터치 + 초기화. 0 성공, 음수 errno. */
int  pace_shm_create(const char *name, pace_shm_t *out);
/* 기존 영역 열기 (헤더·버전 검사). 0 성공. */
int  pace_shm_open(const char *name, pace_shm_t *out);
void pace_shm_close(pace_shm_t *h);
int  pace_shm_unlink(const char *name);

/* 편의 래퍼 */
static inline bool pace_shm_push_msg(pace_shm_t *h, pace_queue_id_t q, const pace_msg_t *m) { return pace_spsc_push(h->queue[q], m); }
static inline bool pace_shm_pop_msg (pace_shm_t *h, pace_queue_id_t q, pace_msg_t *m)       { return pace_spsc_pop(h->queue[q], m); }
static inline void pace_shm_write_state(pace_shm_t *h, const pace_robot_state_t *s)        { pace_seqlock_write(h->state, s); }
static inline bool pace_shm_read_state (pace_shm_t *h, pace_robot_state_t *s)              { return pace_seqlock_read(h->state, s, 64, NULL); }
static inline void pace_shm_write_contract(pace_shm_t *h, const pace_contract_t *c)        { pace_seqlock_write(h->contract, c); }
static inline bool pace_shm_read_contract (pace_shm_t *h, pace_contract_t *c)              { return pace_seqlock_read(h->contract, c, 64, NULL); }
static inline void pace_shm_write_limits(pace_shm_t *h, const pace_hal_limits_t *l)        { pace_seqlock_write(h->limits, l); }
static inline bool pace_shm_read_limits (pace_shm_t *h, pace_hal_limits_t *l)              { return pace_seqlock_read(h->limits, l, 64, NULL); }
static inline bool pace_shm_push_record(pace_shm_t *h, const pace_tick_record_t *r)        { return pace_spsc_push(h->metrics, r); }
static inline bool pace_shm_pop_record (pace_shm_t *h, pace_tick_record_t *r)              { return pace_spsc_pop(h->metrics, r); }
static inline void pace_shm_write_frame(pace_shm_t *h, const pace_frame_t *f)              { pace_seqlock_write(h->frame, f); }
static inline bool pace_shm_read_frame (pace_shm_t *h, pace_frame_t *f)                    { return pace_seqlock_read(h->frame, f, 1024, NULL); }

#ifdef __cplusplus
}
#endif
#endif /* PACE_SHM_H */
