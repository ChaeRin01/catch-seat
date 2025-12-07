# app.py
import os, sys
sys.path.append(os.path.dirname(__file__))

from flask import Flask, render_template, request, redirect, url_for, flash
from models import db, MovieOpenAlert, SeatCancelAlert, User
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

from catalog import CATALOG, MOVIES
from email_utils import send_email
from datetime import datetime

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

# Flask: app context에서 테이블 생성
with app.app_context():
    db.create_all()
    # 디버그 출력(경로/존재 여부 확인용)
    print("DB 경로:", DB_PATH)
    print("DB 존재?", os.path.exists(DB_PATH))
# --------------------------------

# --- SMTP 설정 (환경변수 기반) ---
app.config["SMTP_HOST"] = os.environ.get("CATCHSEAT_SMTP_HOST")
app.config["SMTP_PORT"] = int(os.environ.get("CATCHSEAT_SMTP_PORT", 587))
app.config["SMTP_USER"] = os.environ.get("CATCHSEAT_SMTP_USER")
app.config["SMTP_PASSWORD"] = os.environ.get("CATCHSEAT_SMTP_PASSWORD")
app.config["SMTP_USE_TLS"] = os.environ.get("CATCHSEAT_SMTP_USE_TLS", "true").lower() == "true"
app.config["SMTP_DEFAULT_SENDER"] = os.environ.get("CATCHSEAT_SMTP_DEFAULT_SENDER")

# ★ LoginManager 설정 (보호 라우트 접근 시 /login으로 보냄)
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

# 과제 전용(숨김): 직접 URL로만 접근
@app.get("/hw1")
def hw1():
    return render_template("hw1.html")

@app.get("/select")
def select_service():
    return render_template("service_select.html", title="서비스 선택")

# ---- 알림 폼: DB 저장까지 (지금은 보호 안 함; 다음 단계에서 보호 적용) ----

@app.route("/alerts/open", methods=["GET", "POST"])
@login_required   
def open_alert_form():
    if request.method == "POST":
        movie = request.form.get("movie", "").strip()
        theater = request.form.get("theater", "").strip()
        screen = request.form.get("screen", "").strip()

        if not movie or not theater:
            flash("영화와 극장은 필수입니다.", "error")
            return redirect(url_for("open_alert_form"))

        # DB 저장
        alert = MovieOpenAlert(
            movie=movie,
            theater=theater,
            screen=screen or None,
            user_id=current_user.id
            )
        db.session.add(alert)
        db.session.commit()

        flash(f"[저장됨] 오픈 알림: {movie} / {theater} / {screen or '-'}", "success")
        return redirect(url_for("open_alert_form"))

    return render_template(
        "alerts_open.html",
        title="오픈 알림 신청",
        catalog=CATALOG,
        movies=MOVIES
    )

@app.route("/alerts/seat", methods=["GET", "POST"])
@login_required   
def seat_alert_form():
    if request.method == "POST":
        movie = request.form.get("movie", "").strip()
        theater = request.form.get("theater", "").strip()
        show_dt = request.form.get("show_datetime", "").strip()
        seats = request.form.get("desired_seats", "").strip()

        if not movie or not theater or not show_dt or not seats:
            flash("모든 필드를 입력하세요.", "error")
            return redirect(url_for("seat_alert_form"))

        # DB 저장
        alert = SeatCancelAlert(
            movie=movie,
            theater=theater,
            show_datetime=show_dt,
            desired_seats=seats,
            user_id=current_user.id
            )
        db.session.add(alert)
        db.session.commit()

        flash(f"[저장됨] 좌석 취소 알림: {movie} / {theater} / {show_dt} / {seats}", "success")
        return redirect(url_for("seat_alert_form"))

    return render_template(
        "alerts_seat.html",
        title="좌석 취소 알림 신청",
        catalog=CATALOG,
        movies=MOVIES
    )

# --------------------------------------------------------

# ---------- Auth: signup / login / logout ----------

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
        # ...
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
    return redirect(url_for("index"))
# ---------------------------------------------------

@app.get("/me")
@login_required
def me():
    my_open = MovieOpenAlert.query.filter_by(user_id=current_user.id)\
                                  .order_by(MovieOpenAlert.id.desc()).all()
    my_seat = SeatCancelAlert.query.filter_by(user_id=current_user.id)\
                                   .order_by(SeatCancelAlert.id.desc()).all()

    # 극장 코드 -> 극장 이름(예: 메가박스 코엑스) 매핑해서 템플릿에 넘겨줄 값 세팅
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
    """
    SMTP 설정 및 email_utils.send_email이 실제로 동작하는지 확인하기 위한 테스트용 라우트.
    """
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
    """
    디버그용: 현재 DB에 있는 알림들을 모두 확인하고,
    발송 조건을 만족하는 알림에 대해 이메일을 발송(또는 발송 시도)한다.
    """

    # 순환 import 방지용: 함수 안에서 가져오기
    from models import MovieOpenAlert, SeatCancelAlert, db

    now = datetime.utcnow()
    sent_count = 0
    errors = []

    # 1) 오픈 알림 처리
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
            alert.is_sent = True  # 오픈 알림은 1회 발송 정책
            sent_count += 1
        except Exception as e:
            errors.append(f"OpenAlert id={alert.id}: {e}")

    # 2) 좌석 취소 알림 처리
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
        f"run-checks 완료.",
        f"총 발송 시도 성공 건수: {sent_count}",
    ]
    if errors:
        msg_lines.append("")
        msg_lines.append("에러 목록:")
        msg_lines.extend(errors)

    return "<br>".join(msg_lines)



# -----------------
if __name__ == "__main__":
    app.run()  # http://127.0.0.1:5000
