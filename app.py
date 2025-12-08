import os, sys
sys.path.append(os.path.dirname(__file__))

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
)
from models import db, MovieOpenAlert, SeatCancelAlert, User
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

from catalog import CATALOG, MOVIES
from email_utils import send_email
from datetime import datetime
from crawlers import megabox  # 메가박스 DOLBY 상영정보 크롤링용
import json

app = Flask(__name__)

# --- 메가박스 DOLBY 지점 코드 -> 지점명 매핑 ---
BRANCH_CODE_TO_NAME = {
    "0019": "메가박스 남양주현대아울렛스페이스원",
    "7011": "메가박스 대구신세계(동대구)",
    "0028": "메가박스 대전신세계아트앤사이언스",
    "4062": "메가박스 송도(트리플스트리트)",
    "0052": "메가박스 수원AK플라자(수원역)",
    "0020": "메가박스 안성스타필드",
    "1351": "메가박스 코엑스",
    "4651": "메가박스 하남스타필드",
}

# 세션/플래시
app.config["SECRET_KEY"] = "dev-secret"

# --- DB 설정 (SQLite 파일) ---
BASEDIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASEDIR, "catchseat.db")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + DB_PATH
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

# --- 인기 좌석 구역 요약 데이터 로드 ---
ZONE_PATH = os.path.join(BASEDIR, "data", "seat_zone_summary.json")
try:
    with open(ZONE_PATH, encoding="utf-8") as f:
        ZONE_SUMMARY = json.load(f)
except FileNotFoundError:
    ZONE_SUMMARY = {}


def get_zone_summary(branch_code: str) -> str:
    """브랜치 코드 기준으로 인기 좌석 구역 요약 문구를 반환."""
    entry = ZONE_SUMMARY.get(branch_code)
    return entry["zone_summary"] if entry and "zone_summary" in entry else "인기 구역 데이터가 없습니다."


# --- 돌비시네마 상영관 기본 정보 (좌석 수/열 범위/좌석 번호/특징) ---
DOLBY_THEATER_INFO = {
    "0019": {  # 남양주현대아울렛스페이스원
        "seats": 290,
        "row_range": "A-M",
        "number_range": "1-24번",
        "feature": "국내 돌비 시네마 중에서 평가가 가장 좋은 상영관입니다.",
    },
    "7011": {  # 대구신세계(동대구)
        "seats": 213,
        "row_range": "A-J",
        "number_range": "1-22번",
        "feature": None,
    },
    "0028": {  # 대전신세계아트앤사이언스
        "seats": 313,
        "row_range": "A-M",
        "number_range": "1-26번",
        "feature": "설계 단계부터 돌비 시네마 전용으로 건설된 유일한 상영관입니다.",
    },
    "4062": {  # 송도(트리플스트리트)
        "seats": 285,
        "row_range": "A-L",
        "number_range": "1-25번",
        "feature": None,
    },
    "0052": {  # 수원AK플라자(수원역)
        "seats": 275,
        "row_range": "A-M",
        "number_range": "1-23번",
        "feature": None,
    },
    "0020": {  # 안성스타필드
        "seats": 254,
        "row_range": "A-O",
        "number_range": "1-19번",
        "feature": None,
    },
    "1351": {  # 코엑스
        "seats": 378,
        "row_range": "A-R",
        "number_range": "1-24번",
        "feature": (
            "한국 최초로 도입된 돌비 시네마 상영관입니다. "
            "국내 돌비 시네마 중 유일하게 스코프(2.39:1) 비율의 스크린을 사용하는 상영관입니다. "
            "2023년 기준, 전 세계 275개 돌비 시네마 중 관람객 수 1위를 기록한 상영관입니다."
        ),
    },
    "4651": {  # 하남스타필드
        "seats": 336,
        "row_range": "A-L",
        "number_range": "1-29번",
        "feature": "국내 돌비 시네마 가운데 가장 큰 스크린을 보유한 상영관입니다.",
    },
}

# Flask: app context에서 테이블 생성
with app.app_context():
    db.create_all()
    print("DB 경로:", DB_PATH)
    print("DB 존재?", os.path.exists(DB_PATH))

# --- SMTP 설정 (환경변수 기반) ---
app.config["SMTP_HOST"] = os.environ.get("CATCHSEAT_SMTP_HOST")
app.config["SMTP_PORT"] = int(os.environ.get("CATCHSEAT_SMTP_PORT", 587))
app.config["SMTP_USER"] = os.environ.get("CATCHSEAT_SMTP_USER")
app.config["SMTP_PASSWORD"] = os.environ.get("CATCHSEAT_SMTP_PASSWORD")
app.config["SMTP_USE_TLS"] = os.environ.get("CATCHSEAT_SMTP_USE_TLS", "true").lower() == "true"
app.config["SMTP_DEFAULT_SENDER"] = os.environ.get("CATCHSEAT_SMTP_DEFAULT_SENDER")

# ★ LoginManager 설정
login_manager = LoginManager(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id: str):
    return User.query.get(int(user_id))


@app.get("/")
def index():
    return "This is catch-seat!"


@app.get("/home")
def home():
    return render_template("home.html", title="홈")


@app.get("/hw1")
def hw1():
    return render_template("hw1.html")


@app.get("/select")
def select_service():
    return render_template("service_select.html", title="서비스 선택")


# ---- 메가박스 돌비시네마 소개 페이지 ----
@app.get("/theaters/dolby")
def dolby_theaters():
    """메가박스 돌비시네마 8개 지점 정보 + 인기 좌석 구역 안내 페이지."""
    theaters = []
    for code, name in BRANCH_CODE_TO_NAME.items():
        info = DOLBY_THEATER_INFO.get(code, {})
        theaters.append(
            {
                "code": code,
                "name": name,
                "seats": info.get("seats"),
                "row_range": info.get("row_range"),
                "number_range": info.get("number_range"),
                "feature": info.get("feature"),
                "zone_summary": get_zone_summary(code),
            }
        )
    theaters.sort(key=lambda t: t["name"])
    return render_template(
        "dolby_theaters.html",
        title="메가박스 돌비시네마 안내",
        theaters=theaters,
    )


# ---- 오픈 알림 ----
@app.route("/alerts/open", methods=["GET", "POST"])
@login_required
def open_alert_form():
    if request.method == "POST":
        movie = request.form.get("movie", "").strip()
        theater = request.form.get("theater", "").strip()
        screen = request.form.get("screen", "").strip()
        date_str = request.form.get("date", "").strip()  # "YYYY-MM-DD"

        if not movie or not theater:
            flash("영화와 극장은 필수입니다.", "error")
            return redirect(url_for("open_alert_form"))

        if not date_str:
            flash("관람 날짜를 선택해주세요.", "error")
            return redirect(url_for("open_alert_form"))

        date_compact = date_str.replace("-", "")
        if len(date_compact) != 8 or not date_compact.isdigit():
            flash("관람 날짜 형식이 올바르지 않습니다.", "error")
            return redirect(url_for("open_alert_form"))

        alert = MovieOpenAlert(
            movie=movie,
            theater=theater,
            screen=screen or None,
            user_id=current_user.id,
            date=date_compact,
        )
        db.session.add(alert)
        db.session.commit()

        flash(
            f"[저장됨] 오픈 알림: {movie} / {theater} / {screen or '-'} / {date_str}",
            "success",
        )
        return redirect(url_for("open_alert_form"))

    return render_template(
        "alerts_open.html",
        title="오픈 알림 신청",
        catalog=CATALOG,
        movies=MOVIES,
    )


# ---- 좌석 취소 알림 (폼 + 검색 API) ----
def _parse_seats_status_to_int(seats_status: str) -> int:
    if not seats_status:
        return 0
    seats_status = seats_status.strip()
    if seats_status.startswith("잔여") and seats_status.endswith("석"):
        inner = seats_status[2:-1].strip()
        parts = inner.split()
        if parts:
            try:
                return int(parts[0])
            except ValueError:
                return 0
    return 0


@app.route("/alerts/seat", methods=["GET", "POST"])
@login_required
def seat_alert_form():
    if request.method == "POST":
        brand_raw = request.form.get("brand", "").strip()
        brand = (brand_raw or "MEGABOX").upper()

        movie = request.form.get("movie", "").strip()
        theater = request.form.get("theater", "").strip()  # branch_code
        date_str = request.form.get("date", "").strip()
        show_dt = request.form.get("show_datetime", "").strip()
        screen = request.form.get("screen", "").strip()
        desired_count_raw = request.form.get("desired_count", "").strip()

        if not theater or not date_str:
            flash("극장과 날짜를 먼저 선택하고 상영정보를 검색해주세요.", "error")
            return redirect(url_for("seat_alert_form"))

        if not movie or not show_dt or not screen:
            flash("영화와 상영 시간/상영관을 모두 선택해주세요.", "error")
            return redirect(url_for("seat_alert_form"))

        if not desired_count_raw or not desired_count_raw.isdigit():
            flash("원하는 좌석 수를 1 이상의 정수로 입력해주세요.", "error")
            return redirect(url_for("seat_alert_form"))

        desired_count = int(desired_count_raw)
        if desired_count <= 0:
            flash("원하는 좌석 수는 1 이상이어야 합니다.", "error")
            return redirect(url_for("seat_alert_form"))

        date_compact = date_str.replace("-", "")
        if len(date_compact) != 8 or not date_compact.isdigit():
            flash("관람 날짜 형식이 올바르지 않습니다.", "error")
            return redirect(url_for("seat_alert_form"))

        start_time = None
        if len(show_dt) >= 5:
            maybe_time = show_dt[-5:]
            if ":" in maybe_time:
                start_time = maybe_time

        if not start_time:
            flash("상영 시간 형식이 올바르지 않습니다.", "error")
            return redirect(url_for("seat_alert_form"))

        try:
            showtimes = megabox.get_showtimes(theater, date_compact)
        except Exception as e:
            print("[seat_alert_form] 메가박스 상영정보 크롤링 실패:", e)
            flash("메가박스 상영정보를 불러오는 중 오류가 발생했습니다. 다시 시도해주세요.", "error")
            return redirect(url_for("seat_alert_form"))

        baseline_available = None
        for st in showtimes:
            if st.get("movie_title") != movie:
                continue
            if st.get("screen_name") != screen:
                continue
            if st.get("start_time") != start_time:
                continue
            baseline_available = _parse_seats_status_to_int(st.get("seats_status"))
            break

        if baseline_available is None:
            flash("선택하신 상영 정보를 메가박스에서 찾을 수 없습니다. 다시 검색 후 선택해주세요.", "error")
            return redirect(url_for("seat_alert_form"))

        alert = SeatCancelAlert(
            user_id=current_user.id,
            brand=brand,
            movie=movie,
            theater=theater,
            screen=screen or None,
            show_datetime=show_dt,
            desired_seats=None,
            desired_count=desired_count,
            baseline_available_seats=baseline_available,
            last_available_seats=baseline_available,
        )
        db.session.add(alert)
        db.session.commit()

        flash(
            f"[저장됨] 좌석 취소 알림: {brand} / {movie} / "
            f"{BRANCH_CODE_TO_NAME.get(theater, theater)} / {show_dt} / "
            f"기준 잔여 {baseline_available}석 / 원하는 {desired_count}석",
            "success",
        )
        return redirect(url_for("seat_alert_form"))

    return render_template(
        "alerts_seat.html",
        title="좌석 취소 알림 신청",
        dolby_branches=BRANCH_CODE_TO_NAME,
    )


@app.get("/api/megabox/dolby_showtimes")
@login_required
def api_megabox_dolby_showtimes():
    theater = (request.args.get("theater") or "").strip()
    date_str = (request.args.get("date") or "").strip()

    if not theater or not date_str:
        return jsonify({"ok": False, "error": "극장과 날짜를 모두 선택해주세요."}), 400

    date_compact = date_str.replace("-", "")
    if len(date_compact) != 8 or not date_compact.isdigit():
        return jsonify({"ok": False, "error": "날짜 형식이 올바르지 않습니다."}), 400

    if theater not in BRANCH_CODE_TO_NAME:
        return jsonify({"ok": False, "error": "지원하지 않는 DOLBY 지점입니다."}), 400

    try:
        showtimes = megabox.get_showtimes(theater, date_compact)
    except Exception as e:
        print("[api_megabox_dolby_showtimes] 크롤링 실패:", e)
        return jsonify({"ok": False, "error": "메가박스 상영정보를 불러오는 중 오류가 발생했습니다."}), 500

    return jsonify(
        {"ok": True, "branch_code": theater, "date": date_str, "showtimes": showtimes}
    )


# ---------- Auth ----------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        pw = request.form.get("password", "")
        if not email or not pw:
            flash("이메일/비밀번호를 입력하세요.", "error")
            return redirect(url_for("signup"))
        if User.query.filter_by(email=email).first():
            flash("이미 가입된 이메일입니다.", "error")
            return redirect(url_for("signup"))
        u = User(email=email)
        u.set_password(pw)
        db.session.add(u)
        db.session.commit()
        flash("회원가입 완료. 로그인하세요.", "success")
        return redirect(url_for("login"))
    return render_template("auth_signup.html", title="회원가입")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        pw = request.form.get("password", "")
        u = User.query.filter_by(email=email).first()
        if not u or not u.check_password(pw):
            flash("이메일 또는 비밀번호가 올바르지 않습니다.", "error")
            return redirect(url_for("login"))
        login_user(u)
        flash("로그인되었습니다.", "success")
        nxt = request.args.get("next")
        return redirect(nxt or url_for("select_service"))
    return render_template("auth_login.html", title="로그인")


@app.get("/logout")
@login_required
def logout():
    logout_user()
    flash("로그아웃되었습니다.", "success")
    return redirect(url_for("home"))


# ---------- 마이페이지 ----------
@app.get("/me")
@login_required
def me():
    my_open = (
        MovieOpenAlert.query.filter_by(user_id=current_user.id)
        .order_by(MovieOpenAlert.id.asc())
        .all()
    )
    my_seat = (
        SeatCancelAlert.query.filter_by(user_id=current_user.id)
        .order_by(SeatCancelAlert.id.asc())
        .all()
    )

    for a in my_open:
        a.theater_name = BRANCH_CODE_TO_NAME.get(a.theater, a.theater)
    for a in my_seat:
        a.theater_name = BRANCH_CODE_TO_NAME.get(a.theater, a.theater)

    return render_template("me.html", title="마이페이지", my_open=my_open, my_seat=my_seat)


@app.post("/me/open/<int:alert_id>/delete")
@login_required
def delete_my_open(alert_id):
    a = MovieOpenAlert.query.filter_by(id=alert_id, user_id=current_user.id).first()
    if not a:
        flash("삭제할 항목을 찾을 수 없습니다.", "error")
        return redirect(url_for("me"))
    db.session.delete(a)
    db.session.commit()
    flash("오픈 알림을 삭제했습니다.", "success")
    return redirect(url_for("me"))


@app.post("/me/seat/<int:alert_id>/delete")
@login_required
def delete_my_seat(alert_id):
    a = SeatCancelAlert.query.filter_by(id=alert_id, user_id=current_user.id).first()
    if not a:
        flash("삭제할 항목을 찾을 수 없습니다.", "error")
        return redirect(url_for("me"))
    db.session.delete(a)
    db.session.commit()
    flash("좌석 취소 알림을 삭제했습니다.", "success")
    return redirect(url_for("me"))


@app.route("/debug/test-email")
@login_required
def debug_test_email():
    to = request.args.get("to") or current_user.email
    if not to:
        return "받는 이메일 주소가 없습니다. 쿼리스트링 ?to=... 또는 유저 이메일을 설정하세요.", 400

    subject = "[Catch-Seat] SMTP 테스트 메일"
    body = "이 메일이 도착했다면 Catch-Seat SMTP 설정이 정상 동작 중입니다."

    try:
        send_email(to, subject, body)
    except Exception as e:
        return f"메일 발송 실패: {e}", 500

    return f"테스트 메일을 {to} 로 발송했습니다."


@app.route("/debug/run-checks")
@login_required
def debug_run_checks():
    from models import MovieOpenAlert, SeatCancelAlert, db

    now = datetime.utcnow()
    sent_count = 0
    errors = []

    open_alerts = MovieOpenAlert.query.filter_by(active=True).all()
    for alert in open_alerts:
        alert.last_checked = now
        if not alert.can_send_now(now):
            continue
        user = alert.user
        if not user or not user.email:
            continue

        subject = f"[Catch-Seat] 영화 오픈 알림 - {alert.movie} / {alert.theater}"
        body_lines = [
            "안녕하세요, Catch-Seat 입니다.",
            "",
            "요청하신 '영화 오픈 알림' 조건에 해당하는 변화가 감지되었습니다.",
            f"- 영화: {alert.movie}",
            f"- 극장: {alert.theater}",
            f"- 상영관: {alert.screen or '상영관 미지정'}",
            "",
            "자세한 예매 상황은 공식 예매 페이지에서 직접 확인해 주세요.",
            "",
            "Catch-Seat 드림",
        ]
        body = "\n".join(body_lines)

        try:
            send_email(user.email, subject, body)
            alert.sent_at = now
            alert.send_count = (alert.send_count or 0) + 1
            alert.is_sent = True
            sent_count += 1
        except Exception as e:
            errors.append(f"OpenAlert id={alert.id}: {e}")

    seat_alerts = SeatCancelAlert.query.filter_by(active=True).all()
    for alert in seat_alerts:
        alert.last_checked = now
        if not alert.can_send_now(now):
            continue
        user = alert.user
        if not user or not user.email:
            continue

        subject = f"[Catch-Seat] 좌석 취소 알림 - {alert.movie} / {alert.theater}"
        body_lines = [
            "안녕하세요, Catch-Seat 입니다.",
            "",
            "요청하신 '좌석 취소 알림' 조건에 해당하는 변화가 감지되었습니다.",
            f"- 영화: {alert.movie}",
            f"- 극장: {alert.theater}",
            f"- 상영 시간: {alert.show_datetime}",
            f"- 원하는 좌석: {alert.desired_seats}",
            "",
            "정확한 잔여 좌석 상황은 공식 예매 페이지에서 확인해 주세요.",
            "",
            "Catch-Seat 드림",
        ]
        body = "\n".join(body_lines)

        try:
            send_email(user.email, subject, body)
            alert.sent_at = now
            alert.send_count = (alert.send_count or 0) + 1
            alert.is_sent = True
            sent_count += 1
        except Exception as e:
            errors.append(f"SeatAlert id={alert.id}: {e}")

    db.session.commit()

    msg_lines = [
        "run-checks 완료.",
        f"총 발송 시도 성공 건수: {sent_count}",
    ]
    if errors:
        msg_lines.append("")
        msg_lines.append("에러 목록:")
        msg_lines.extend(errors)

    return "<br>".join(msg_lines)


if __name__ == "__main__":
    app.run()
