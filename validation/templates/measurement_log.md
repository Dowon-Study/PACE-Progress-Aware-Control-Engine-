# 측정 기록 양식 (configs/ 에 측정 1건당 1파일, 파일명은 raw 와 동일하게)

- 날짜/시각:
- 측정자:
- 플랫폼 버전 (git hash / 전달받은 파일명):
- 커널: `uname -r` →
- 커널 파라미터: `cat /proc/cmdline` →
- governor: `cat /sys/devices/system/cpu/cpu4/cpufreq/scaling_governor` →
- 격리 조건: none / isol / ccx
- 부하 조건: idle / stress / ai-gpu / full
  - 부하 명령 (stress-ng 옵션, AI 실행 명령 등):
- 지속시간:
- 회차:
- 측정 명령 (복사해서 그대로 다시 돌릴 수 있게):
- 동시에 실행 중이던 다른 프로그램:
- 결과 파일: raw/
- 특이사항 (튄 값, 중단, 재시작 등):
