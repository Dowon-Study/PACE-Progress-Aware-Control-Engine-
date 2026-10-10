/*
 * HAL 백엔드: ros2_control hardware_interface 플러그인 (제조사 비종속 HAL 의 "번역" 층)
 *  - URDF 의 <ros2_control> 태그를 ResourceManager 로 읽어 pluginlib 로 하드웨어 플러그인을 적재/활성화한다.
 *  - 실시간 루프에서 부르는 read/write 는 ResourceManager::read/write 만 호출 (할당 없음). 플러그인의 RT 품질은 루프가 계약(wcet)으로 측정한다.
 *  - 정지 3단계: DECEL = 램프 명령 그대로, HOLD = 마지막 상태 위치 명령, ESTOP = HOLD + 체결 플래그 (플러그인에 비상정지 인터페이스가 없으면 이 의미로 강등하고 폴트 비트로 보고)
 *  - controller_manager 는 쓰지 않는다 (docs/IDEA_FIXED.md 11절). ROS 2 통신은 초기화에만 (rclcpp::init, 로거).
 */
#include <chrono>
#include <cstring>
#include <fstream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>
#include <rclcpp/rclcpp.hpp>
#include <hardware_interface/resource_manager.hpp>
#include <hardware_interface/component_parser.hpp>
#include <hardware_interface/types/lifecycle_state_names.hpp>
#include <rclcpp_lifecycle/state.hpp>
#include <lifecycle_msgs/msg/state.hpp>
extern "C" {
#include "pace/hal.h"
#include "pace/rt.h"
}

namespace {
struct Ctx {
    std::unique_ptr<hardware_interface::ResourceManager> rm;
    std::shared_ptr<rclcpp::Clock> clock;
    std::vector<std::string> joints;
    std::vector<hardware_interface::LoanedCommandInterface> cmd_pos, cmd_vel;
    std::vector<hardware_interface::LoanedStateInterface> st_pos, st_vel, st_eff;
    pace_hal_limits_t limits{};
    double q_last[PACE_MAX_DOF]{};
    bool estop = false, have_state = false;
    uint64_t lag = 0;
    rclcpp::Duration period{0, 1000000};
};

int ros2_init(pace_hal_t *h, const char *arg)
{
    auto *c = static_cast<Ctx *>(h->ctx);
    if (!arg) return -1;
    std::ifstream f(arg); if (!f) { fprintf(stderr, "[hal_ros2] cannot open URDF %s\n", arg); return -2; }
    std::stringstream ss; ss << f.rdbuf(); std::string urdf = ss.str();
    if (!rclcpp::ok()) rclcpp::init(0, nullptr);
    c->clock = std::make_shared<rclcpp::Clock>(RCL_STEADY_TIME);
    try {
        c->rm = std::make_unique<hardware_interface::ResourceManager>(urdf, c->clock, rclcpp::get_logger("pace_hal_ros2"), /*activate_all=*/true, /*update_rate=*/1000);
    } catch (const std::exception &e) { fprintf(stderr, "[hal_ros2] ResourceManager: %s\n", e.what()); return -3; }
    if (!c->rm->are_components_initialized()) { fprintf(stderr, "[hal_ros2] components not initialized\n"); return -4; }
    /* 관절 목록·한계는 URDF(<joint><limit>)에서: HAL 공통 데이터 구조로 번역 */
    auto infos = hardware_interface::parse_control_resources_from_urdf(urdf);
    std::memset(&c->limits, 0, sizeof c->limits);
    c->limits.native_period_ns = 1000000; c->limits.read_wcet_ns = 50000; c->limits.write_wcet_ns = 50000; c->limits.accepts_position = 1;
    for (int k = 0; k < 3; ++k) { c->limits.workspace_min[k] = -2.0f; c->limits.workspace_max[k] = 2.0f; }
    for (auto &info : infos) {
        auto it = info.hardware_parameters.find("read_wcet_us"); if (it != info.hardware_parameters.end()) c->limits.read_wcet_ns = (uint32_t)(std::stod(it->second) * 1e3);
        it = info.hardware_parameters.find("write_wcet_us"); if (it != info.hardware_parameters.end()) c->limits.write_wcet_ns = (uint32_t)(std::stod(it->second) * 1e3);
        for (auto &j : info.joints) {
            if (c->joints.size() >= PACE_MAX_DOF) break;
            int i = (int)c->joints.size(); c->joints.push_back(j.name);
            c->limits.q_min[i] = -6.3f; c->limits.q_max[i] = 6.3f; c->limits.qd_max[i] = 3.15f; c->limits.qdd_max[i] = 20.0f; c->limits.jerk_max[i] = 500.0f; c->limits.tau_max[i] = 150.0f;
            auto lt = info.limits.find(j.name);
            if (lt != info.limits.end()) {
                const auto &L = lt->second;
                if (L.has_position_limits) { c->limits.q_min[i] = (float)L.min_position; c->limits.q_max[i] = (float)L.max_position; }
                if (L.has_velocity_limits) c->limits.qd_max[i] = (float)L.max_velocity;
                if (L.has_acceleration_limits) c->limits.qdd_max[i] = (float)L.max_acceleration;
                if (L.has_jerk_limits) c->limits.jerk_max[i] = (float)L.max_jerk;
                if (L.has_effort_limits) c->limits.tau_max[i] = (float)L.max_effort;
            }
        }
    }
    c->limits.dof = (uint16_t)c->joints.size();
    try {
        for (auto &n : c->joints) {
            c->cmd_pos.push_back(c->rm->claim_command_interface(n + "/position"));
            if (c->rm->command_interface_exists(n + "/velocity")) c->cmd_vel.push_back(c->rm->claim_command_interface(n + "/velocity"));   /* 속도 피드포워드 (있으면) */
            c->st_pos.push_back(c->rm->claim_state_interface(n + "/position"));
            if (c->rm->state_interface_exists(n + "/velocity")) c->st_vel.push_back(c->rm->claim_state_interface(n + "/velocity"));
            if (c->rm->state_interface_exists(n + "/effort")) c->st_eff.push_back(c->rm->claim_state_interface(n + "/effort"));
        }
    } catch (const std::exception &e) { fprintf(stderr, "[hal_ros2] claim: %s\n", e.what()); return -5; }
    c->limits.accepts_velocity = c->cmd_vel.size() == c->joints.size(); c->limits.accepts_effort = 0;
    fprintf(stderr, "[hal_ros2] %zu components, %u joints, velocity state %s, velocity command %s, wcet read/write %u/%u us\n", infos.size(), c->limits.dof, c->st_vel.size() == c->joints.size() ? "yes" : "no", c->limits.accepts_velocity ? "yes" : "no", c->limits.read_wcet_ns / 1000, c->limits.write_wcet_ns / 1000);
    return 0;
}
void ros2_shutdown(pace_hal_t *h)
{
    auto *c = static_cast<Ctx *>(h->ctx);
    try { c->cmd_pos.clear(); c->st_pos.clear(); c->st_vel.clear(); c->st_eff.clear(); if (c->rm) c->rm->shutdown_components(); c->rm.reset(); } catch (const std::exception &e) { fprintf(stderr, "[hal_ros2] shutdown: %s\n", e.what()); }
    if (rclcpp::ok()) rclcpp::shutdown();
}
int ros2_read(pace_hal_t *h, pace_robot_state_t *st)
{
    auto *c = static_cast<Ctx *>(h->ctx);
    auto rs = c->rm->read(c->clock->now(), c->period);
    std::memset(st, 0, sizeof *st);
    st->t_ns = pace_now_ns(); st->dof = c->limits.dof; st->valid = 1;
    for (uint16_t i = 0; i < st->dof; ++i) { auto v = c->st_pos[i].get_optional(); st->q[i] = (float)v.value_or(c->q_last[i]); c->q_last[i] = st->q[i]; }
    if (c->st_vel.size() == c->joints.size()) { st->valid |= 2; for (uint16_t i = 0; i < st->dof; ++i) st->qd[i] = (float)c->st_vel[i].get_optional().value_or(0.0); }
    if (c->st_eff.size() == c->joints.size()) { st->valid |= 8; for (uint16_t i = 0; i < st->dof; ++i) st->tau[i] = (float)c->st_eff[i].get_optional().value_or(0.0); }
    if (rs.result != hardware_interface::return_type::OK) st->hal_fault |= PACE_HALF_COMM;
    if (c->estop) st->hal_fault |= PACE_HALF_ESTOP_LATCHED;
    c->have_state = true;
    return 0;
}
int ros2_write(pace_hal_t *h, uint64_t, uint16_t, const float *q, const float *qd, uint16_t dof)
{
    auto *c = static_cast<Ctx *>(h->ctx);
    if (c->estop) { for (uint16_t i = 0; i < c->limits.dof; ++i) { (void)c->cmd_pos[i].set_value(c->q_last[i]); if (c->limits.accepts_velocity) (void)c->cmd_vel[i].set_value(0.0); } }
    else for (uint16_t i = 0; i < dof && i < c->limits.dof; ++i) { (void)c->cmd_pos[i].set_value((double)q[i]); if (c->limits.accepts_velocity) (void)c->cmd_vel[i].set_value(qd ? (double)qd[i] : 0.0); }
    auto ws = c->rm->write(c->clock->now(), c->period);
    return ws.result == hardware_interface::return_type::OK ? 0 : 1;
}
int ros2_stop(pace_hal_t *h, uint64_t, pace_stop_level_t level)
{
    auto *c = static_cast<Ctx *>(h->ctx);
    if (level == PACE_STOP_ESTOP) c->estop = true;                      /* 체결: 이후 write 는 마지막 위치 유지. 플러그인 고유 비상정지 인터페이스가 있으면 여기서 호출 */
    for (uint16_t i = 0; i < c->limits.dof; ++i) { (void)c->cmd_pos[i].set_value(c->q_last[i]); if (c->limits.accepts_velocity) (void)c->cmd_vel[i].set_value(0.0); }
    auto ws = c->rm->write(c->clock->now(), c->period);
    return ws.result == hardware_interface::return_type::OK ? 0 : 1;
}
const pace_hal_limits_t *ros2_limits(pace_hal_t *h) { return &static_cast<Ctx *>(h->ctx)->limits; }
uint64_t ros2_lag(pace_hal_t *h) { return static_cast<Ctx *>(h->ctx)->lag; }
}  // namespace

extern "C" pace_hal_t *pace_hal_ros2_create(void)
{
    auto *h = new pace_hal_t(); auto *c = new Ctx();
    h->name = "ros2_control"; h->ctx = c;
    h->init = ros2_init; h->shutdown = ros2_shutdown; h->read = ros2_read; h->write = ros2_write; h->stop = ros2_stop;
    h->limits = ros2_limits; h->backend_lag_ticks = ros2_lag;
    return h;
}
