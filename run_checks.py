"""
run_checks.py

메가박스 DOLBY 영화 오픈 알림 & 좌석 취소 알림 체크 스크립트

1) 영화 오픈 알림 (MovieOpenAlert)
   - MovieOpenAlert들을 조회
   - 지점(theater, = Megabox brchNo) + 날짜별로 묶어서
     crawlers.megabox.get_showtimes() 호출
   - 각 alert에 대해 megabox.is_open_now(alert, showtimes)를 이용해
     "예매 오픈 여부" 판단
   - 조건을 만족하면 콘솔에 표시하고, 알림 상태 필드 갱신
   - ✅ 예매 오픈(TRIGGER) 시 사용자에게 메일 발송

2) 좌석 취소 알림 (SeatCancelAlert)
   - SeatCancelAlert 중 active=True, is_sent=False 조회
   - show_datetime 기준으로 날짜(YYYYMMDD)를 뽑아서
     지점 + 날짜별로 get_showtimes() 한 번만 호출
   - 영화 제목, 상영관, 시간(HHMM)으로 상영 회차를 매칭
   - 해당 showtime의 seats_status("잔여 152석")에서 잔여 좌석 수 추출
   - ✅ (current_available - baseline_available_seats) >= desired_count
       인 경우 메일 발송 및 상태 필드 갱신

SMTP 환경변수:
    CATCHSEAT_SMTP_HOST
    CATCHSEAT_SMTP_PORT
    CATCHSEAT_SMTP_USER
    CATCHSEAT_SMTP_PASSWORD (또는 CATCHSEAT_SMTP_PASS)
    CATCHSEAT_SMTP_USE_TLS
    CATCHSEAT_SMTP_DEFAULT_SENDER
"""

import os
import datetime
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr

from app import app           # Flask 앱 객체
from models import db, MovieOpenAlert, SeatCancelAlert
from crawlers import megabox


# --- 지점 코드 → 지점 이름 매핑 (DOLBY 8개) ---
BRANCH_CODE_TO_NAME = {
    "0019": "메가박스 남양주현대아울렛스페이스원",
    "7011": "메가박스 대구신세계(동대구)",
    "0028": "메가박스 대전신세계 아트앤사이언스",
    "4062": "메가박스 송도(트리플스트리트)",
    "0052": "메가박스 수원AK플라자(수원역)",
    "0020": "메가박스 안성스타필드",
    "1351": "메가박스 코엑스",
    "4651": "메가박스 하남스타필드",
}


# --- SMTP / 메일 설정 (환경변수 사용) ---
SMTP_HOST = os.environ.get("CATCHSEAT_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("CATCHSEAT_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("CATCHSEAT_SMTP_USER")
SMTP_PASS = (
    os.environ.get("CATCHSEAT_SMTP_PASS")
    or os.environ.get("CATCHSEAT_SMTP_PASSWORD")
)
SMTP_USE_TLS = os.environ.get("CATCHSEAT_SMTP_USE_TLS", "true").lower() == "true"
SMTP_DEFAULT_SENDER = os.environ.get("CATCHSEAT_SMTP_DEFAULT_SENDER")

if SMTP_DEFAULT_SENDER:
    SENDER_HEADER = SMTP_DEFAULT_SENDER
else:
    SENDER_HEADER = f"Catch-Seat Alert Service <{SMTP_USER or ''}>"


def _get_alert_recipient_email(alert) -> str | None:
    """
    알림 인스턴스에서 수신자 이메일을 추출한다.
    - 우선 alert.user.email을 시도
    - 없으면 alert.email 필드도 시도

    MovieOpenAlert, SeatCancelAlert 둘 다 공통 인터페이스를 쓴다고 가정.
    """
    user = getattr(alert, "user", None)
    if user is not None:
        email = getattr(user, "email", None)
        if email:
            return email

    email = getattr(alert, "email", None)
    if email:
        return email

    return None


# ---------------------------------------------------------------------------
#   1) 오픈 알림 (MovieOpenAlert) 메일 발송
# ---------------------------------------------------------------------------

def send_open_alert_email(
    alert: MovieOpenAlert,
    real_movie_title: str | None = None,
    theater_name: str | None = None,
) -> bool:
    """
    영화 예매 오픈 시, 해당 알림 대상자에게 메일을 전송한다.

    real_movie_title : 실제 편성에 잡힌 영화 제목 (예: '주토피아 2')
    theater_name     : 지점명 (예: '메가박스 코엑스')

    반환값:
        True  -> 메일 전송 성공
        False -> 전송 실패 (SMTP 설정 누락/오류 등)
    """

    if not SMTP_USER or not SMTP_PASS:
        print("[run_checks] ⚠ SMTP 환경변수(CATCHSEAT_SMTP_USER / "
              "CATCHSEAT_SMTP_PASS 또는 CATCHSEAT_SMTP_PASSWORD)가 설정되어 있지 않아 "
              "메일을 전송하지 않습니다.")
        return False

    to_email = _get_alert_recipient_email(alert)
    if not to_email:
        print(f"[run_checks] ⚠ MovieOpenAlert id={alert.id} 에 연결된 수신자 이메일이 없습니다. 메일 전송 생략.")
        return False

    keyword = alert.movie                          # 사용자가 입력한 키워드 (예: '주토피아')
    movie_title = real_movie_title or keyword      # 실제 영화 제목 (없으면 키워드와 동일하게)
    branch_code = alert.theater
    screen = alert.screen

    # 지점명 표시
    theater_label = (
        theater_name
        or BRANCH_CODE_TO_NAME.get(branch_code, f"메가박스 지점({branch_code})")
    )

    # 현재 서비스는 메가박스 DOLBY 전용이므로 브랜드 라벨은 고정
    brand_label = "메가박스"

    # alert에 date 필드가 있으면 사용, 없으면 오늘 날짜로 표시
    alert_date = getattr(alert, "date", None)
    if isinstance(alert_date, datetime.date):
        date_str = alert_date.strftime("%Y-%m-%d")
    elif alert_date:
        # 문자열인 경우 "YYYYMMDD" 또는 "YYYY-MM-DD" 둘 다 수용
        s = str(alert_date)
        if len(s) == 8 and s.isdigit():
            date_str = f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
        else:
            date_str = s
    else:
        date_str = datetime.date.today().strftime("%Y-%m-%d")

    subject = f"[Catch-Seat] '{movie_title}' 예매가 열렸어요!"
    body = (
        f"안녕하세요, Catch-Seat입니다.\n\n"
        f"요청하신 영화 예매 오픈 알림을 알려드립니다.\n\n"
        f"알림신청 키워드: {keyword}\n"
        f"영화: {movie_title}\n"
        f"영화관: {theater_label}\n"
        f"상영관: {screen}\n"
        f"날짜: {date_str}\n\n"
        f"{brand_label} 예매 페이지에서 좌석 상황을 확인해 주세요.\n\n"
        f"- 이 메일은 자동 발송되었습니다."
    )

    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = SENDER_HEADER
    msg["To"] = to_email

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            if SMTP_USE_TLS:
                server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, [to_email], msg.as_string())

        print(f"[run_checks] ✉ 메일 전송 완료: to={to_email}, MovieOpenAlert id={alert.id}")
        return True

    except Exception as e:
        print(f"[run_checks] ❌ 메일 전송 실패: to={to_email}, MovieOpenAlert id={alert.id}, error={e}")
        return False


def _get_alert_date_str(alert: MovieOpenAlert, today_yyyymmdd: str) -> str:
    """
    알림별로 사용할 날짜 문자열(YYYYMMDD)을 결정.
    - alert.date가 있으면 그걸 사용 (date객체/문자열 모두 대응)
    - 없으면 today_yyyymmdd 사용
    """
    alert_date = getattr(alert, "date", None)

    if isinstance(alert_date, datetime.date):
        return alert_date.strftime("%Y%m%d")
    if isinstance(alert_date, str) and alert_date.strip():
        return alert_date.strip().replace("-", "")
    return today_yyyymmdd


def _extract_real_movie_title(alert: MovieOpenAlert, showtimes: list) -> str | None:
    """
    showtimes 리스트에서 alert.movie 키워드가 포함된 실제 영화 제목을 찾아 반환.
    (키 이름은 프로젝트 구조에 따라 'movie_title' / 'title' / 'movie' 등을 시도)
    """
    keyword = (alert.movie or "").strip()
    if not keyword:
        return None

    for st in showtimes:
        if not isinstance(st, dict):
            continue
        title = (
            st.get("movie_title")
            or st.get("title")
            or st.get("movie")
            or ""
        )
        if keyword in title:
            return title

    return None


def run_movie_open_checks():
    """메가박스 DOLBY 기반 영화 오픈 알림 전체 체크"""

    today_yyyymmdd = datetime.date.today().strftime("%Y%m%d")

    with app.app_context():
        alerts = (
            MovieOpenAlert.query
            .filter_by(active=True)
            .all()
        )

        if not alerts:
            print("[run_checks] 활성화된 MovieOpenAlert 가 없습니다.")
            return

        print(f"[run_checks] 활성화된 MovieOpenAlert 개수: {len(alerts)}")
        print(f"[run_checks] 오늘 날짜 기준(기본값): {today_yyyymmdd}")

        # 지점 + 날짜별 그룹핑
        grouped = {}  # (branch_code, date_yyyymmdd) -> [alerts...]

        for alert in alerts:
            branch_code = (alert.theater or "").strip()
            if not branch_code:
                print(f"  - [경고] MovieOpenAlert id={alert.id} 에 theater(지점 코드)가 없습니다. 건너뜀.")
                continue

            date_yyyymmdd = _get_alert_date_str(alert, today_yyyymmdd)
            key = (branch_code, date_yyyymmdd)
            grouped.setdefault(key, []).append(alert)

        # 각 (지점, 날짜)마다 한 번만 크롤링
        for (branch_code, date_yyyymmdd), alerts_in_group in grouped.items():
            theater_name = BRANCH_CODE_TO_NAME.get(branch_code)

            print(
                f"\n[run_checks] Megabox DOLBY 체크: "
                f"branch_code={branch_code}, date={date_yyyymmdd}, alerts={len(alerts_in_group)}개"
            )

            try:
                showtimes = megabox.get_showtimes(branch_code, date_yyyymmdd)
            except Exception as e:
                print(f"  - [에러] 메가박스 크롤링 실패: {e}")
                continue

            print(f"  - get_showtimes() → DOLBY 상영 {len(showtimes)}개")

            now = datetime.datetime.utcnow()
            triggered_any = False

            for alert in alerts_in_group:
                if not alert.can_send_now(now=now):
                    print(f"    · MovieOpenAlert id={alert.id} (movie='{alert.movie}') "
                          f"→ can_send_now=False, 건너뜀.")
                    continue

                is_open = megabox.is_open_now(alert, showtimes)

                if not is_open:
                    print(f"    · MovieOpenAlert id={alert.id} (movie='{alert.movie}') "
                          f"→ 아직 예매 오픈 아님.")
                    continue

                # 여기까지 왔으면 "예매 오픈" 조건 만족
                triggered_any = True

                # 실제 영화 제목 추출
                real_title = _extract_real_movie_title(alert, showtimes)

                print(f"    ✅ [TRIGGER-OPEN] MovieOpenAlert id={alert.id} / "
                      f"keyword='{alert.movie}' / real_title='{real_title or alert.movie}' / "
                      f"theater='{alert.theater}' / screen='{alert.screen}'")

                # 메일 발송 시도 (알림 키워드 + 실제 제목 + 지점명 포함)
                mail_ok = send_open_alert_email(
                    alert,
                    real_movie_title=real_title,
                    theater_name=theater_name,
                )

                if mail_ok:
                    alert.is_sent = True
                    alert.sent_at = now
                    alert.send_count = (alert.send_count or 0) + 1
                    alert.last_checked = now
                else:
                    alert.last_checked = now

            if triggered_any:
                db.session.commit()
                print("  - [OPEN] 트리거된 알림이 있어 DB에 변경 내용을 커밋했습니다.")
            else:
                print("  - [OPEN] 이번 실행에서 트리거된 알림은 없습니다.")


# ---------------------------------------------------------------------------
#   2) 좌석 취소 알림(SeatCancelAlert) run_checks 구현
# ---------------------------------------------------------------------------

def _get_date_from_show_datetime(show_dt, fallback_yyyymmdd: str) -> str:
    """
    SeatCancelAlert.show_datetime 에서 날짜(YYYYMMDD)를 뽑아낸다.
    - datetime 인 경우: 그대로 포맷
    - 문자열인 경우: 숫자만 모아서 앞 8자리 사용 (예: '2025-12-08 18:30' -> '20251208')
    - 실패 시 fallback_yyyymmdd 사용
    """
    if isinstance(show_dt, datetime.datetime):
        return show_dt.strftime("%Y%m%d")

    if isinstance(show_dt, datetime.date):
        return show_dt.strftime("%Y%m%d")

    if isinstance(show_dt, str) and show_dt.strip():
        s = "".join(ch for ch in show_dt if ch.isdigit())
        if len(s) >= 8:
            return s[:8]

    return fallback_yyyymmdd


def _get_time_hm_from_show_datetime(show_dt) -> str | None:
    """
    SeatCancelAlert.show_datetime 에서 'HHMM' 형태의 시간 문자열을 추출.
    - datetime: '%H%M'
    - 문자열: 숫자만 모아 뒤에서 4자리 사용 (예: '202512081830' -> '1830')
    - 실패 시 None
    """
    if isinstance(show_dt, datetime.datetime):
        return show_dt.strftime("%H%M")

    if isinstance(show_dt, str) and show_dt.strip():
        digits = "".join(ch for ch in show_dt if ch.isdigit())
        if len(digits) >= 4:
            return digits[-4:]

    return None


def _normalize_screen_name(name: str | None) -> str:
    """
    상영관 이름 비교를 위한 간단 정규화:
    - 공백 제거
    """
    if not name:
        return ""
    return "".join(name.split())


def _extract_time_hm_from_showtime(st: dict) -> str | None:
    """
    크롤링된 showtime dict에서 상영 시작 시간을 'HHMM' 형식으로 추출.
    실제 구조에 맞춰 'start_time'을 우선 사용한다.
    """
    if not isinstance(st, dict):
        return None

    candidate = (
        st.get("start_time")          # 실제 키: '09:15'
        or st.get("time")
        or st.get("start_datetime")
        or st.get("datetime")
        or st.get("show_time")
    )

    if isinstance(candidate, datetime.datetime):
        return candidate.strftime("%H%M")

    if isinstance(candidate, str) and candidate.strip():
        digits = "".join(ch for ch in candidate if ch.isdigit())
        if len(digits) >= 4:
            return digits[-4:]

    return None


def _match_showtime_for_seat_alert(alert: SeatCancelAlert, showtimes: list) -> dict | None:
    """
    SeatCancelAlert가 가리키는 상영 회차에 해당하는 showtime dict 한 개를 찾는다.

    매칭 기준 (최대한 보수적으로):
    - 영화 제목: alert.movie 가 showtime['movie_title'] 등 title 계열 키에 포함
    - 상영관 이름: alert.screen 과 showtime['screen_name'] 등 screen 계열 키가
                   (공백 제거 후) 일치
    - 상영 시간(HHMM): alert.show_datetime 기반 'HHMM' 과 showtime 시간 'HHMM' 일치
    """
    keyword = (alert.movie or "").strip()
    target_screen = _normalize_screen_name(getattr(alert, "screen", None))
    target_time_hm = _get_time_hm_from_show_datetime(getattr(alert, "show_datetime", None))

    for st in showtimes:
        if not isinstance(st, dict):
            continue

        # 영화 제목 매칭
        title = (
            st.get("movie_title")      # 실제 키
            or st.get("title")
            or st.get("movie")
            or ""
        )
        if keyword and keyword not in title:
            continue

        # 상영관 이름 비교
        st_screen = (
            st.get("screen_name")      # 실제 키
            or st.get("screen")
            or st.get("theater_screen")
            or st.get("theater_name2")
        )
        norm_st_screen = _normalize_screen_name(st_screen)

        if target_screen and norm_st_screen and target_screen != norm_st_screen:
            continue

        # 시간 비교
        st_time_hm = _extract_time_hm_from_showtime(st)
        if target_time_hm and st_time_hm and target_time_hm != st_time_hm:
            continue

        # 위 조건들을 통과한 첫 showtime을 매칭 결과로 사용
        return st

    return None


def _get_available_seats_from_show(st: dict) -> int | None:
    """
    showtime dict에서 '현재 잔여 좌석 수'를 추출.

    실제 Megabox DOLBY 크롤러 구조:
        'seats_status': '잔여 152석'
    형태를 우선적으로 파싱한다.
    """
    if not isinstance(st, dict):
        return None

    # 1) 실제 확인된 키: seats_status = "잔여 152석"
    status = st.get("seats_status")
    if isinstance(status, str) and status.strip():
        digits = "".join(ch for ch in status if ch.isdigit())
        if digits:
            return int(digits)

    # 2) 혹시 모를 다른 숫자형 필드들에 대한 보조 처리 (있으면 사용, 없으면 무시)
    candidate_keys = [
        "available_seats",
        "remain_cnt",
        "remaining_seats",
        "seat_remain_cnt",
        "seat_count_remain",
    ]

    for key in candidate_keys:
        v = st.get(key)
        if isinstance(v, (int, float)):
            if v >= 0:
                return int(v)
        elif isinstance(v, str) and v.strip().isdigit():
            val = int(v.strip())
            if val >= 0:
                return val

    return None


def send_seat_cancel_email(
    alert: SeatCancelAlert,
    theater_name: str | None,
    baseline_available: int,
    current_available: int,
    desired_count: int,
) -> bool:
    """
    좌석 취소 알림 조건 충족 시 사용자에게 메일 발송.

    - baseline_available: 기준 시점 잔여 좌석 수
    - current_available : 현재 잔여 좌석 수
    - desired_count     : 사용자가 원하는 좌석 수
    """

    if not SMTP_USER or not SMTP_PASS:
        print("[run_checks] ⚠ SMTP 환경변수(CATCHSEAT_SMTP_USER / "
              "CATCHSEAT_SMTP_PASS 또는 CATCHSEAT_SMTP_PASSWORD)가 설정되어 있지 않아 "
              "메일을 전송하지 않습니다.")
        return False

    to_email = _get_alert_recipient_email(alert)
    if not to_email:
        print(f"[run_checks] ⚠ SeatCancelAlert id={alert.id} 에 연결된 수신자 이메일이 없습니다. 메일 전송 생략.")
        return False

    movie_title = (alert.movie or "").strip() or "(제목 미지정)"
    branch_code = (alert.theater or "").strip()
    screen = getattr(alert, "screen", None) or "(상영관 미지정)"

    theater_label = (
        theater_name
        or BRANCH_CODE_TO_NAME.get(branch_code, f"메가박스 지점({branch_code})")
    )

    brand_label = "메가박스"

    show_dt = getattr(alert, "show_datetime", None)
    if isinstance(show_dt, datetime.datetime):
        dt_str = show_dt.strftime("%Y-%m-%d %H:%M")
    elif isinstance(show_dt, datetime.date):
        dt_str = show_dt.strftime("%Y-%m-%d")
    else:
        dt_str = str(show_dt) if show_dt else "(상영 시간 미지정)"

    diff = current_available - baseline_available

    subject = f"[Catch-Seat] 좌석이 다시 풀렸어요! - {movie_title} / {theater_label}"
    body = (
        f"안녕하세요, Catch-Seat입니다.\n\n"
        f"요청하신 좌석 취소 알림 조건을 만족하는 상영 회차가 발견되었습니다.\n\n"
        f"영화: {movie_title}\n"
        f"영화관: {theater_label}\n"
        f"상영관: {screen}\n"
        f"상영 일시: {dt_str}\n\n"
        f"기준 잔여 좌석 수(baseline): {baseline_available}석\n"
        f"현재 잔여 좌석 수: {current_available}석\n"
        f"증가한 좌석 수: {diff}석\n"
        f"{brand_label} 예매 페이지에서 좌석 상황을 확인해 주세요.\n\n"
        f"- 이 메일은 자동 발송되었습니다."
    )

    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = SENDER_HEADER
    msg["To"] = to_email

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            if SMTP_USE_TLS:
                server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, [to_email], msg.as_string())

        print(f"[run_checks] ✉ 메일 전송 완료: to={to_email}, SeatCancelAlert id={alert.id}")
        return True

    except Exception as e:
        print(f"[run_checks] ❌ 메일 전송 실패: to={to_email}, SeatCancelAlert id={alert.id}, error={e}")
        return False


def run_seat_cancel_checks():
    """
    메가박스 DOLBY 기반 좌석 취소 알림 전체 체크.

    트리거 조건:
        (current_available - baseline_available_seats) >= desired_count
    """

    today_yyyymmdd = datetime.date.today().strftime("%Y%m%d")

    with app.app_context():
        alerts = (
            SeatCancelAlert.query
            .filter_by(active=True, is_sent=False)
            .all()
        )

        if not alerts:
            print("[run_checks] 활성화된 SeatCancelAlert 가 없습니다.")
            return

        print(f"[run_checks] 활성화된 SeatCancelAlert 개수: {len(alerts)}")

        # 지점 + 날짜별 그룹핑 (show_datetime 기준)
        grouped: dict[tuple[str, str], list[SeatCancelAlert]] = {}

        for alert in alerts:
            branch_code = (getattr(alert, "theater", "") or "").strip()
            if not branch_code:
                print(f"  - [경고] SeatCancelAlert id={alert.id} 에 theater(지점 코드)가 없습니다. 건너뜀.")
                continue

            show_dt = getattr(alert, "show_datetime", None)
            date_yyyymmdd = _get_date_from_show_datetime(show_dt, today_yyyymmdd)
            key = (branch_code, date_yyyymmdd)
            grouped.setdefault(key, []).append(alert)

        # 각 (지점, 날짜)마다 한 번만 크롤링
        for (branch_code, date_yyyymmdd), alerts_in_group in grouped.items():
            theater_name = BRANCH_CODE_TO_NAME.get(branch_code)

            print(
                f"\n[run_checks] Megabox DOLBY 좌석 취소 체크: "
                f"branch_code={branch_code}, date={date_yyyymmdd}, alerts={len(alerts_in_group)}개"
            )

            try:
                showtimes = megabox.get_showtimes(branch_code, date_yyyymmdd)
            except Exception as e:
                print(f"  - [에러] 메가박스 크롤링 실패: {e}")
                continue

            print(f"  - get_showtimes() → DOLBY 상영 {len(showtimes)}개")

            now = datetime.datetime.utcnow()
            triggered_any = False
            updated_any = False

            for alert in alerts_in_group:
                if not alert.can_send_now(now=now):
                    print(f"    · SeatCancelAlert id={alert.id} (movie='{alert.movie}') "
                          f"→ can_send_now=False, 건너뜀.")
                    continue

                baseline = getattr(alert, "baseline_available_seats", None)
                desired = getattr(alert, "desired_count", None)

                if baseline is None:
                    print(f"    · SeatCancelAlert id={alert.id} → baseline_available_seats가 없습니다. 건너뜀.")
                    continue
                if desired is None or desired <= 0:
                    print(f"    · SeatCancelAlert id={alert.id} → desired_count가 유효하지 않습니다. 건너뜀.")
                    continue

                matched_show = _match_showtime_for_seat_alert(alert, showtimes)
                if not matched_show:
                    print(f"    · SeatCancelAlert id={alert.id} → 매칭되는 상영 회차를 찾지 못했습니다.")
                    continue

                current_available = _get_available_seats_from_show(matched_show)

                # --- 여기부터 매진(0석) 처리 추가 ---
                if current_available is None:
                    seats_status = str(matched_show.get("seats_status", "")).strip()
                    if "매진" in seats_status:
                        # 매진인 경우는 0석으로 간주
                        current_available = 0
                    else:
                        print(f"    · SeatCancelAlert id={alert.id} → showtime에서 잔여 좌석 수를 읽지 못했습니다.")
                        continue
                # --- 매진 처리 끝 ---

                diff = current_available - baseline

                print(
                    f"    · SeatCancelAlert id={alert.id} / movie='{alert.movie}' / "
                    f"screen='{alert.screen}' / baseline={baseline}, current={current_available}, "
                    f"desired={desired}, diff={diff}"
                )

                # 항상 last_available_seats & last_checked 업데이트
                alert.last_available_seats = current_available
                alert.last_checked = now
                updated_any = True

                if diff >= desired:
                    # 트리거 조건 충족
                    triggered_any = True

                    print(f"    ✅ [TRIGGER-SEAT] SeatCancelAlert id={alert.id} → 조건 만족, 메일 발송 시도")

                    mail_ok = send_seat_cancel_email(
                        alert,
                        theater_name=theater_name,
                        baseline_available=baseline,
                        current_available=current_available,
                        desired_count=desired,
                    )

                    if mail_ok:
                        alert.is_sent = True
                        alert.sent_at = now
                        alert.send_count = (alert.send_count or 0) + 1

            if triggered_any or updated_any:
                db.session.commit()
                if triggered_any:
                    print("  - [SEAT] 트리거된 알림 및 상태 변경을 DB에 커밋했습니다.")
                else:
                    print("  - [SEAT] 트리거는 없지만 last_available_seats/last_checked 갱신을 커밋했습니다.")
            else:
                print("  - [SEAT] 이번 실행에서 변경된 알림이 없습니다.")


# ---------------------------------------------------------------------------
#   메인 엔트리 포인트
#   python3 run_checks.py 실행 시 두 알림을 모두 체크
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # 1) 영화 예매 오픈 알림 체크
    run_movie_open_checks()

    # 2) 좌석 취소 알림 체크
    run_seat_cancel_checks()
