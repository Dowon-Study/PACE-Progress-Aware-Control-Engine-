# 측정 체크리스트 (측정 1건마다 복사해서 체크)

측정 이름: `____________________`  (raw/ 파일명과 동일)   날짜: `________`   담당: `________`

## 측정 전
- [ ] `uname -r` 에 `realtime` 이 들어 있다 (RT 커널로 부팅됨)
- [ ] `cat /sys/devices/system/cpu/isolated` → `4-7,20-23` (CCX 격리 적용)
- [ ] `cat /sys/devices/system/cpu/cpu4/cpufreq/scaling_governor` → `performance`
- [ ] 브라우저·IDE·채팅 등 측정과 무관한 프로그램을 모두 닫았다 ("다섯 번째 부하" 방지)
- [ ] 부하 조건이면 부하 명령 앞에 `taskset -c 8-15,24-31` 이 붙어 있다 (CPU4 침범 금지)
- [ ] 부하를 켠 뒤 30초 기다렸다 (`top` → `1` 로 CPU4 사용률 0% 근처 확인)
- [ ] 같은 이름의 raw 파일이 이미 없다 (있으면 회차 r2, r3 로)
- [ ] 플랫폼 버전(git hash 또는 전달받은 파일명)을 적어 두었다

## 측정 중
- [ ] 측정 시작 시각을 기록했다
- [ ] 키보드·마우스를 건드리지 않았다 (10분 측정은 자리를 비워도 된다)

## 측정 후
- [ ] raw 파일 머리말에 `# kernel`, `# cmdline`, `# governor`, `# load`, `# cmd`, `# start` 가 있다
- [ ] `configs/<같은 이름>.md` 를 채웠다 (부하 명령, 특이사항 포함)
- [ ] `verify.py` 를 돌려 요약이 나왔다 (오류 없이)
- [ ] 결과가 상식적이다: n ≈ 1000 × 초, min 이 0 이 아니다, max 가 avg 보다 크다
- [ ] 100μs 초과가 있으면 그 시각·횟수를 특이사항에 적었다 (지우지 않는다)
- [ ] 그림 파일이 열린다 (`out/` 또는 `validation/figures/`)
- [ ] raw 파일을 수정하지 않았다 (분석은 전부 스크립트로)

## 제어루프 로그(ctrl.csv)일 때 추가
- [ ] 같은 이름의 `.trace.bin`, `.summary.json`, `.fake.log`(또는 `--fault-at` 값)를 함께 받았다
- [ ] 장애 주입 시각을 `--fault-t0` 로 넘겼다 (B3)
- [ ] 거부 건수가 주입한 이상값 개수와 맞는다 (B1 교차 확인)
- [ ] 상태 띠 순서가 설계와 같다 (fresh → pacing/local/extrap → hold → stop → recover → fresh)
- [ ] 리포트에 포맷(pace / contract)과 A5 근사 여부를 적었다
