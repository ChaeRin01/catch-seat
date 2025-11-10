# app.py
import os, sys
sys.path.append(os.path.dirname(__file__))  # 로컬 모듈 탐색 안전장치

from flask import Flask, render_template, request, redirect, url_for, flash
from models import db, MovieOpenAlert, SeatCancelAlert, User
from flask_login import LoginManager, login_user, logout_user, login_required, current_user  # ★ 추가

app = Flask(__name__)

# 세션/플래시
app.config["SECRET_KEY"] = "dev-secret"

# --- DB 설정 (SQLite 파일) ---
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///catchseat.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

# Flask 3.x: app context에서 테이블 생성
with app.app_context():
    db.create_all()
# --------------------------------

# ★ LoginManager 설정 (보호 라우트 접근 시 /login으로 보냄)
login_manager = LoginManager(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id: str):
    return User.query.get(int(user_id))

@app.get("/")
def index():
    return "Hello, Flask!"

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
        alert = MovieOpenAlert(movie=movie, theater=theater, screen=screen or None)
        db.session.add(alert)
        db.session.commit()

        flash(f"[저장됨] 오픈 알림: {movie} / {theater} / {screen or '-'}", "success")
        return redirect(url_for("open_alert_form"))

    return render_template("alerts_open.html", title="오픈 알림 신청")

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
            movie=movie, theater=theater,
            show_datetime=show_dt, desired_seats=seats
        )
        db.session.add(alert)
        db.session.commit()

        flash(f"[저장됨] 좌석 취소 알림: {movie} / {theater} / {show_dt} / {seats}", "success")
        return redirect(url_for("seat_alert_form"))

    return render_template("alerts_seat.html", title="좌석 취소 알림 신청")

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
def logout():
    logout_user()
    flash("로그아웃되었습니다.", "success")
    return redirect(url_for("index"))
# ---------------------------------------------------


if __name__ == "__main__":
    app.run()  # http://127.0.0.1:5000
