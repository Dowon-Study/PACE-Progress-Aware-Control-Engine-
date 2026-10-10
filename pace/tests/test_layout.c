/* 레이아웃 덤프: Python ctypes 미러와 바이트 단위 비교에 쓴다. JSON 한 줄 출력. */
#include <stdio.h>
#include <stddef.h>
#include "pace/shm.h"
int main(void)
{
    printf("{");
    printf("\"msg\":%zu,\"header\":%zu,\"path\":%zu,\"path_s\":%zu,\"correction\":%zu,\"param\":%zu,\"event\":%zu,\"contract\":%zu,",
        sizeof(pace_msg_t), sizeof(pace_msg_header_t), sizeof(pace_path_t), sizeof(pace_path_s_t), sizeof(pace_correction_t),
        sizeof(pace_param_t), sizeof(pace_event_t), sizeof(pace_contract_t));
    printf("\"state\":%zu,\"limits\":%zu,\"record\":%zu,\"frame\":%zu,\"spsc\":%zu,\"seqlock\":%zu,\"shm_header\":%zu,\"shm_total\":%zu,",
        sizeof(pace_robot_state_t), sizeof(pace_hal_limits_t), sizeof(pace_tick_record_t), sizeof(pace_frame_t),
        sizeof(pace_spsc_t), sizeof(pace_seqlock_t), sizeof(pace_shm_header_t), pace_shm_total_bytes());
    printf("\"off\":{\"hdr_seq\":%zu,\"hdr_t_gen\":%zu,\"hdr_conf\":%zu,\"hdr_supplier\":%zu,\"hdr_n_points\":%zu,\"body\":%zu,",
        offsetof(pace_msg_header_t, seq), offsetof(pace_msg_header_t, t_gen_ns), offsetof(pace_msg_header_t, confidence),
        offsetof(pace_msg_header_t, supplier), offsetof(pace_msg_header_t, n_points), offsetof(pace_msg_t, body));
    printf("\"path_pts\":%zu,\"path_s_pts\":%zu,\"corr_pts\":%zu,\"param_params\":%zu,",
        offsetof(pace_path_t, pts), offsetof(pace_path_s_t, pts), offsetof(pace_correction_t, pts), offsetof(pace_param_t, params));
    printf("\"rec_stage\":%zu,\"rec_progress\":%zu,\"rec_mode\":%zu,\"rec_triggers\":%zu,",
        offsetof(pace_tick_record_t, stage_ns), offsetof(pace_tick_record_t, progress_s), offsetof(pace_tick_record_t, mode), offsetof(pace_tick_record_t, triggers));
    printf("\"spsc_tail\":%zu,\"spsc_capacity\":%zu,\"spsc_mask\":%zu,\"seqlock_data_size\":%zu,\"frame_data\":%zu}",
        offsetof(pace_spsc_t, tail), offsetof(pace_spsc_t, capacity), offsetof(pace_spsc_t, mask), offsetof(pace_seqlock_t, data_size), offsetof(pace_frame_t, data));
    printf("}\n");
    return 0;
}
