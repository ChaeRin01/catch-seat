"""
run_checks.py

메가박스 DOLBY 영화 오픈 알림 체크 스크립트 (MVP + 메일 발송)

- MovieOpenAlert들을 조회
- 지점(theater, = Megabox brchNo) + 날짜별로 묶어서
  crawlers.megabox.get_showtimes() 호출
- 각 alert에 대해 megabox.is_open_now(alert, showtimes)를 이용해
  "예매 오픈 여부" 판단
- 조건을 만족하면 콘솔에 표시하고, 알림 상태 필드 갱신
- ✅ 예매 오픈(TRIGGER) 시 사용자에게 메일 발송

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
from models import db, MovieOpenAlert
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


def _get_alert_recipient_email(alert: MovieOpenAlert) -> str | None:
    """
    MovieOpenAlert 인스턴스에서 수신자 이메일을 추출한다.
    - 우선 alert.user.email을 시도
    - 없으면 alert.email 필드도 시도
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
        print(f"[run_checks] ⚠ alert id={alert.id} 에 연결된 수신자 이메일이 없습니다. 메일 전송 생략.")
        return False

    keyword = alert.movie                          # 사용자가 입력한 키워드 (예: '주토피아')
    movie_title = real_movie_title or keyword      # 실제 영화 제목 (없으면 키워드와 동일하게)
    branch_code = alert.theater
    screen = alert.screen

    # 지점명 표시
    # 우선 인자로 받은 theater_name을 쓰고, 없으면 코드 기반 매핑 사용
    theater_label = (
        theater_name
        or BRANCH_CODE_TO_NAME.get(branch_code, f"메가박스 지점({branch_code})")
    )

    # alert에 date 필드가 있으면 사용, 없으면 오늘 날짜로 표시
    alert_date = getattr(alert, "date", None)
    if isinstance(alert_date, datetime.date):
        date_str = alert_date.strftime("%Y-%m-%d")
    elif alert_date:
        date_str = str(alert_date)
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
        f"메가박스 예매 페이지에서 좌석 상황을 확인해 주세요.\n\n"
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

        print(f"[run_checks] ✉ 메일 전송 완료: to={to_email}, alert id={alert.id}")
        return True

    except Exception as e:
        print(f"[run_checks] ❌ 메일 전송 실패: to={to_email}, alert id={alert.id}, error={e}")
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
                print(f"  - [경고] alert id={alert.id} 에 theater(지점 코드)가 없습니다. 건너뜀.")
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
                    print(f"    · alert id={alert.id} (movie='{alert.movie}') "
                          f"→ can_send_now=False, 건너뜀.")
                    continue

                is_open = megabox.is_open_now(alert, showtimes)

                if not is_open:
                    print(f"    · alert id={alert.id} (movie='{alert.movie}') "
                          f"→ 아직 예매 오픈 아님.")
                    continue

                # 여기까지 왔으면 "예매 오픈" 조건 만족
                triggered_any = True

                # 실제 영화 제목 추출
                real_title = _extract_real_movie_title(alert, showtimes)

                print(f"    ✅ [TRIGGER] alert id={alert.id} / "
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
                print("  - 트리거된 알림이 있어 DB에 변경 내용을 커밋했습니다.")
            else:
                print("  - 이번 실행에서 트리거된 알림은 없습니다.")


if __name__ == "__main__":
    run_movie_open_checks()
