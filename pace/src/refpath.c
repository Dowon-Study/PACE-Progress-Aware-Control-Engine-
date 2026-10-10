#include "pace/refpath.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

int pace_refpath_load(pace_refpath_t *r, const char *path)
{
    FILE *f = fopen(path, "rb"); if (!f) return -1;
    uint32_t magic = 0, n = 0; float hdr[4];
    if (fread(&magic, 4, 1, f) != 1 || magic != 0x48545052u || fread(&n, 4, 1, f) != 1 || n < 2 || n > PACE_REFPATH_MAX || fread(hdr, 4, 4, f) != 4) { fclose(f); return -2; }
    r->n = n; r->sdot_nominal = hdr[0]; r->standoff = hdr[1]; r->travel_angle = hdr[2];
    for (uint32_t i = 0; i < n; ++i) { float row[7]; if (fread(row, 4, 7, f) != 7) { fclose(f); return -3; } r->s[i] = row[0]; memcpy(r->pos[i], row + 1, 12); memcpy(r->tan[i], row + 4, 12); }
    fclose(f); return 0;
}
float pace_refpath_length(const pace_refpath_t *r) { return r->s[r->n - 1]; }

bool pace_refpath_eval(const pace_refpath_t *r, float s, float pos[3], float tan[3], float nrm[3])
{
    uint32_t n = r->n; bool end = false;
    if (s <= r->s[0]) { memcpy(pos, r->pos[0], 12); memcpy(tan, r->tan[0], 12); }
    else if (s >= r->s[n - 1]) { memcpy(pos, r->pos[n - 1], 12); memcpy(tan, r->tan[n - 1], 12); end = true; }
    else {
        uint32_t lo = 0, hi = n - 1;                                     /* 이분 탐색 (log n) */
        while (hi - lo > 1) { uint32_t mid = (lo + hi) / 2; if (r->s[mid] <= s) lo = mid; else hi = mid; }
        float a = (s - r->s[lo]) / (r->s[hi] - r->s[lo] + 1e-12f);
        for (int k = 0; k < 3; ++k) { pos[k] = r->pos[lo][k] + a * (r->pos[hi][k] - r->pos[lo][k]); tan[k] = r->tan[lo][k] + a * (r->tan[hi][k] - r->tan[lo][k]); }
    }
    float tn = sqrtf(tan[0] * tan[0] + tan[1] * tan[1] + tan[2] * tan[2]) + 1e-12f; for (int k = 0; k < 3; ++k) tan[k] /= tn;
    nrm[0] = -tan[1]; nrm[1] = tan[0]; nrm[2] = 0.0f;                   /* ẑ × t (xy 평면) */
    float nn = sqrtf(nrm[0] * nrm[0] + nrm[1] * nrm[1]) + 1e-12f; nrm[0] /= nn; nrm[1] /= nn;
    return end;
}

float pace_refpath_project(const pace_refpath_t *r, const float p[3])
{
    float best = 1e30f; uint32_t bi = 0;
    for (uint32_t i = 0; i < r->n; ++i) { float dx = p[0] - r->pos[i][0], dy = p[1] - r->pos[i][1]; float d2 = dx * dx + dy * dy; if (d2 < best) { best = d2; bi = i; } }
    return r->s[bi];
}
