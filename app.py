# app.py
import os, sys
sys.path.append(os.path.dirname(__file__))  # 로컬 모듈 탐색 안전장치(필수는 아님)

from flask import Flask, render_template, request, redirect, url_for, flash
from models import db, MovieOpenAlert, SeatCancelAlert

app = Flask(__name__)

# 세션/플래시
app.config["SECRET_KEY"] = "dev-secret"

# --- DB 설정 (SQLite 파일) ---
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///catchseat.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

# Flask 3.x: before_first_request 제거됨 → 앱 컨텍스트에서 직접 생성
with app.app_context():
    db.create_all()
# --------------------------------

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

# ---- 알림 폼: DB 저장까지 ----

@app.route("/alerts/open", methods=["GET", "POST"])
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

if __name__ == "__main__":
    app.run()  # http://127.0.0.1:5000
