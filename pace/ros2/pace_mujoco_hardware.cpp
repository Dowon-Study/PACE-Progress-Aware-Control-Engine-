/*
 * ros2_control SystemInterface 플러그인: PACE 의 공유메모리 락스텝 MuJoCo 시뮬(pace_sim)을 ros2_control 하드웨어로 노출한다.
 * "자체 MuJoCo 백엔드 2종" 중 두 번째: 같은 시뮬을 ros2_control 플러그인 API 를 통해 구동 → 1kHz 루프가 플러그인 경로로도 같은 로봇을 돌린다.
 * 파라미터: simlink (기본 /pace_sim). 상태: position/velocity/effort, 명령: position.
 */
#include <string>
#include <vector>
#include <cstring>
#include <hardware_interface/system_interface.hpp>
#include <hardware_interface/types/hardware_interface_type_values.hpp>
#include <pluginlib/class_list_macros.hpp>
extern "C" {
#include "pace/sim_link.h"
#include "pace/rt.h"
}

namespace pace_mujoco_hardware {
class PaceMujocoSystem : public hardware_interface::SystemInterface {
public:
    hardware_interface::CallbackReturn on_init(const hardware_interface::HardwareInfo &info) override
    {
        if (SystemInterface::on_init(info) != hardware_interface::CallbackReturn::SUCCESS) return hardware_interface::CallbackReturn::ERROR;
        auto it = info_.hardware_parameters.find("simlink"); simlink_ = it != info_.hardware_parameters.end() ? it->second : "/pace_sim";
        has_vel_cmd_ = true; for (auto &j : info_.joints) { bool v = false; for (auto &ci : j.command_interfaces) if (ci.name == "velocity") v = true; if (!v) has_vel_cmd_ = false; }
        return hardware_interface::CallbackReturn::SUCCESS;
    }
    hardware_interface::CallbackReturn on_activate(const rclcpp_lifecycle::State &) override
    {
        if (pace_sim_link_open(simlink_.c_str(), &link_)) return hardware_interface::CallbackReturn::ERROR;
        for (int i = 0; i < 300 && !pace_sim_link_read_state(link_, &ss_); ++i) pace_sleep_until_ns(pace_now_ns() + 10000000);
        publish_state(); for (size_t i = 0; i < info_.joints.size(); ++i) { (void)set_command(info_.joints[i].name + "/position", (double)ss_.st.q[i]); if (has_vel_cmd_) (void)set_command(info_.joints[i].name + "/velocity", 0.0); }
        return hardware_interface::CallbackReturn::SUCCESS;
    }
    hardware_interface::CallbackReturn on_deactivate(const rclcpp_lifecycle::State &) override
    {
        if (link_) { pace_sim_link_close(link_); link_ = nullptr; }
        return hardware_interface::CallbackReturn::SUCCESS;
    }
    hardware_interface::return_type read(const rclcpp::Time &, const rclcpp::Duration &) override
    {
        if (!link_) return hardware_interface::return_type::ERROR;
        if (!pace_sim_link_read_state(link_, &ss_)) { ++stale_; publish_state(); return hardware_interface::return_type::OK; }   /* 새 상태가 아직 없으면 지난 상태 유지 (일시적; ERROR 를 돌려주면 ros2_control 이 컴포넌트를 영구 비활성화한다) */
        publish_state(); return hardware_interface::return_type::OK;
    }
    hardware_interface::return_type write(const rclcpp::Time &, const rclcpp::Duration &) override
    {
        if (!link_) return hardware_interface::return_type::ERROR;
        pace_sim_cmd_t cmd; std::memset(&cmd, 0, sizeof cmd);
        cmd.tick = ++tick_; cmd.t_cmd_ns = pace_now_ns(); cmd.dof = (uint16_t)info_.joints.size(); cmd.mode = 0; cmd.stop_level = 0;
        for (size_t i = 0; i < info_.joints.size() && i < PACE_MAX_DOF; ++i) { cmd.q_cmd[i] = (float)get_command(info_.joints[i].name + "/position"); if (has_vel_cmd_) cmd.qd_cmd[i] = (float)get_command(info_.joints[i].name + "/velocity"); }
        pace_sim_link_send_cmd(link_, &cmd); return hardware_interface::return_type::OK;
    }
private:
    void publish_state()
    {
        for (size_t i = 0; i < info_.joints.size() && i < PACE_MAX_DOF; ++i) {
            const std::string &n = info_.joints[i].name;
            (void)set_state(n + "/position", (double)ss_.st.q[i]); (void)set_state(n + "/velocity", (double)ss_.st.qd[i]); (void)set_state(n + "/effort", (double)ss_.st.tau[i]);
        }
    }
    std::string simlink_; pace_sim_link_t *link_ = nullptr; pace_sim_state_t ss_{}; uint64_t tick_ = 0, stale_ = 0; bool has_vel_cmd_ = false;
};
}  // namespace pace_mujoco_hardware
PLUGINLIB_EXPORT_CLASS(pace_mujoco_hardware::PaceMujocoSystem, hardware_interface::SystemInterface)
