/*
 * 기준 경로 (교시/CAD 경로): 호 길이 s 로 매개화된 툴 위치·접선. 파일에서 로드 (비실시간), 평가는 할당 없음.
 * 파일 형식 (리틀엔디언): u32 magic 'RPTH', u32 n, f32 sdot_nominal, f32 standoff, f32 travel_angle, f32 pad, 그 뒤 n × [s, x, y, z, tx, ty, tz] f32
 * CORRECTION 적용: target = p(s) + lat·n(s) + h·ẑ,  n(s) = ẑ × t(s) (접선의 왼쪽, datagen 의 가로 오프셋 규약과 같은 축)
 */
#ifndef PACE_REFPATH_H
#define PACE_REFPATH_H
#include <stdint.h>
#include <stdbool.h>
#ifdef __cplusplus
extern "C" {
#endif
#define PACE_REFPATH_MAX 4096
typedef struct {
    uint32_t n; float sdot_nominal, standoff, travel_angle;
    float s[PACE_REFPATH_MAX], pos[PACE_REFPATH_MAX][3], tan[PACE_REFPATH_MAX][3];
} pace_refpath_t;
int  pace_refpath_load(pace_refpath_t *r, const char *path);          /* 0 성공 */
/* s 에서 위치·접선·법선(왼쪽) 보간. s 범위 밖은 끝점 유지. 반환: 끝에 도달했으면 true */
bool pace_refpath_eval(const pace_refpath_t *r, float s, float pos[3], float tan[3], float nrm[3]);
float pace_refpath_length(const pace_refpath_t *r);
/* 점 p 에 가장 가까운 s (초기 투영용, 전 구간 탐색) */
float pace_refpath_project(const pace_refpath_t *r, const float p[3]);
#ifdef __cplusplus
}
#endif
#endif
