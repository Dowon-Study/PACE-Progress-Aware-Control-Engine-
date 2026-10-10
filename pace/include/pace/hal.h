/*
 * HAL 공통 인터페이스 (docs/IDEA_FIXED.md 3절·7절의 "HAL 계층")
 *  - 실시간 루프는 이 함수 포인터만 부른다. 백엔드가 MuJoCo 인지 EtherCAT 인지 모른다.
 *  - RT 계약: read/write/stop 은 할당·블로킹 없이 limits()->read_wcet_ns / write_wcet_ns 안에 끝나야 한다.
 *    루프가 실제 소요를 측정해 계약 위반을 기록한다.
 *  - ros2_control hardware_interface 로의 어댑터는 이 인터페이스 위에 얹는다 (8단계).
 */
#ifndef PACE_HAL_H
#define PACE_HAL_H
#include <stdint.h>
#include "pace/state.h"
#ifdef __cplusplus
extern "C" {
#endif

typedef struct pace_hal pace_hal_t;
struct pace_hal {
    const char *name;
    void *ctx;
    int  (*init)(pace_hal_t *h, const char *arg);                 /* 비실시간 컨텍스트에서 호출 */
    void (*shutdown)(pace_hal_t *h);
    int  (*read)(pace_hal_t *h, pace_robot_state_t *st);          /* 0 또는 폴트 코드 */
    int  (*write)(pace_hal_t *h, uint64_t tick, uint16_t mode, const float *q_cmd, const float *qd_cmd, uint16_t dof);
    int  (*stop)(pace_hal_t *h, uint64_t tick, pace_stop_level_t level);
    const pace_hal_limits_t *(*limits)(pace_hal_t *h);
    /* 진단 (비실시간에서 읽어도 됨) */
    uint64_t (*backend_lag_ticks)(pace_hal_t *h);                 /* 마지막 read 가 몇 틱 묵은 상태였나 */
};

/* 백엔드 */
pace_hal_t *pace_hal_sim_shm_create(void);   /* arg: sim_link 이름 (예: "/pace_sim") */
pace_hal_t *pace_hal_ros2_create(void);      /* arg: <ros2_control> 태그가 든 URDF 경로. ros2_control hardware_interface 플러그인을 pluginlib 로 적재 (PACE_HAVE_ROS2 빌드에서만) */

#ifdef __cplusplus
}
#endif
#endif
