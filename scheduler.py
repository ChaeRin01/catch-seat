import os
import sys
import datetime
import subprocess
from typing import Tuple

from apscheduler.schedulers.blocking import BlockingScheduler


# 프로젝트 루트 경로 (이 파일이 프로젝트 루트에 있다고 가정)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# run_checks.py 경로
RUN_CHECKS_PATH = os.path.join(PROJECT_ROOT, "run_checks.py")


def parse_run_checks_output(stdout: str) -> Tuple[int, int, int]:
    """
    run_checks.py의 stdout 문자열을 받아서
    - 활성화된 MovieOpenAlert 개수
    - 트리거된 알림 개수
    - 에러 메시지 개수
    를 대략적으로 집계한다.

    ※ run_checks.py의 로그 포맷을 "문자열 기준"으로 파싱하는 방식이라
      포맷이 조금 달라지면 숫자가 안 맞을 수 있음.
    """
    active_alerts_count = 0
    triggered_count = 0
    error_count = 0

    for line in stdout.splitlines():
        line = line.strip()

        # 활성화된 MovieOpenAlert 개수 라인
        # 예) [run_checks] 활성화된 MovieOpenAlert 개수: 2
        if "활성화된 MovieOpenAlert 개수" in line:
            # 맨 끝의 숫자만 추출 시도
            parts = line.split(":")
            if len(parts) >= 2:
                try:
                    active_alerts_count = int(parts[-1].strip())
                except ValueError:
                    pass

        # 트리거 라인
        # 예) ✅ [TRIGGER] alert id=3 / movie='주토피아 2' / theater='1351' / screen='DOLBY CINEMA'
        if "[TRIGGER]" in line:
            triggered_count += 1

        # 에러 라인
        # 예)   - [에러] 메가박스 크롤링 실패: ...
        if "[에러]" in line or "실패" in line:
            error_count += 1

    return active_alerts_count, triggered_count, error_count


def run_movie_open_checks():
    """
    MovieOpenAlert 전체를 검사하는 기존 run_checks.py를
    서브프로세스로 실행하는 래퍼 함수.
    APScheduler가 이 함수를 주기적으로 호출한다.
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[scheduler] {now} - run_checks.py 실행 시작")

    # Python 인터프리터는 현재 인터프리터(sys.executable)를 그대로 사용
    cmd = [sys.executable, RUN_CHECKS_PATH]

    try:
        completed = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )

        print("[scheduler] run_checks.py 실행 성공")
        print("========== run_checks.py stdout ==========")
        stdout = (completed.stdout or "").strip()
        if stdout:
            print(stdout)
        else:
            print("(표시할 stdout이 없습니다.)")
        print("=============== (stdout 끝) =============")

        if completed.stderr.strip():
            print("========== run_checks.py stderr ==========")
            print(completed.stderr.strip())
            print("=============== (stderr 끝) =============")

        # --- 여기서 run_checks.py 출력 요약 ---
        active_alerts, triggered, errors = parse_run_checks_output(stdout)
        print("\n---------- 실행 요약 (scheduler) ----------")
        print(f"· 활성화된 MovieOpenAlert 개수 (추정): {active_alerts}")
        print(f"· 이번 실행에서 트리거된 알림 수: {triggered}")
        print(f"· 에러/실패 로그 라인 수: {errors}")
        print("-----------------------------------------\n")

    except subprocess.CalledProcessError as e:
        print("[scheduler] run_checks.py 실행 실패")
        print(f"  - returncode: {e.returncode}")
        print("---------- 실패 stdout ----------")
        print((e.stdout or "").strip())
        print("---------- 실패 stderr ----------")
        print((e.stderr or "").strip())


def main():
    """
    APScheduler를 이용해 일정 간격으로 run_movie_open_checks를 실행한다.
    """
    scheduler = BlockingScheduler(timezone="Asia/Seoul")

    # 🔁 주기 설정: minutes=10 이 기본
    #   - 테스트할 땐 1로 바꿔도 됨.
    scheduler.add_job(
        run_movie_open_checks,
        "interval",
        minutes=10,
        id="movie_open_checks",
        max_instances=1,   # 동시에 두 번 이상 겹쳐 돌지 않도록
        coalesce=True,     # 밀린 실행은 한 번으로 합치기
    )

    print("[scheduler] APScheduler 시작")
    print("[scheduler] 10분 간격으로 run_checks.py를 실행합니다.")
    print("[scheduler] 첫 실행을 바로 한 번 수행합니다.\n")

    # 서버 띄우자마자 한 번 즉시 실행
    run_movie_open_checks()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n[scheduler] 종료 신호 감지, 스케줄러를 종료합니다.")


if __name__ == "__main__":
    main()
