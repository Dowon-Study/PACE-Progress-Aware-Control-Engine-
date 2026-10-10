/*
 * 운동학 (툴 공간 ↔ 관절 공간). MuJoCo 모델을 운동학 전용으로 사용 (물리 적분 없음).
 *  - 생성은 비실시간에서(모델 로드, mjData 할당). FK/IK 는 할당 없음, 실측 수십 μs → 1kHz 루프에서 호출 가능 (WCET 계측 대상)
 *  - IK: 감쇠 최소제곱, 웜스타트(직전 해), 틱당 반복 수 제한. 목표가 1ms 에 조금만 움직이므로 1~3 회면 수렴
 *  - 로봇 비종속: 모델 XML 과 툴 사이트 이름만 바꾸면 Panda 등에 그대로 적용 (HAL 공통 데이터 구조의 일부)
 */
#ifndef PACE_KIN_H
#define PACE_KIN_H
#include <stdint.h>
#define PACE_KIN_MAXDOF 8
#ifdef __cplusplus
extern "C" {
#endif
typedef struct pace_kin pace_kin_t;
pace_kin_t *pace_kin_create(const char *model_xml, const char *tool_site, char *err, int errlen);
void        pace_kin_destroy(pace_kin_t *k);
int         pace_kin_dof(const pace_kin_t *k);
/* 순기구학: 관절 → 툴 위치(3) + 쿼터니언(4, w x y z) + 회전행렬(9, 행 우선) */
void pace_kin_fk(pace_kin_t *k, const float *q, float pos[3], float quat[4], float rot9[9]);
/* 역기구학 한 스텝 묶음: q_in 에서 iters 회 DLS. 결과 q_out, 위치/자세 오차 반환. 관절 범위 클리핑 */
void pace_kin_ik(pace_kin_t *k, const float *q_in, const float pos[3], const float rot9[9], int iters, float damping,
                 float *q_out, float *err_pos, float *err_rot);
/* 접선·진행각으로 툴 회전행렬 (datagen.trajectory.tool_rotation 과 동일 규약: x=접선, z=아래로 travel_angle 기울임) */
void pace_kin_tool_rotation(const float tangent[3], float travel_angle, float rot9[9]);
#ifdef __cplusplus
}
#endif
#endif
