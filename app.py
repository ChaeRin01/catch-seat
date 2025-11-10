from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)

# 플래시 메시지/세션 사용을 위해 필요 (추후 환경변수로 분리 권장)
app.config["SECRET_KEY"] = "dev-secret"

@app.get("/")
def index():
    return "Hello, Flask!"

@app.get("/home")
def home():
    return render_template("home.html", title="홈")

# 과제 전용: 네비에는 숨김, 직접 URL로만 접근
@app.get("/hw1")
def hw1():
    return render_template("hw1.html")

@app.get("/select")
def select_service():
    return render_template("service_select.html", title="서비스 선택")

# ---- 알림 폼: 최소 동작(POST + 유효성 + 플래시 + PRG) ----

@app.route("/alerts/open", methods=["GET", "POST"])
def open_alert_form():
    if request.method == "POST":
        movie = request.form.get("movie", "").strip()
        theater = request.form.get("theater", "").strip()
        screen = request.form.get("screen", "").strip()

        # 기본 유효성 검사
        if not movie or not theater:
            flash("영화와 극장은 필수입니다.", "error")
            return redirect(url_for("open_alert_form"))  # PRG: POST → Redirect → GET

        # (다음 커밋에서 DB 저장 예정)
        flash(f"오픈 알림 신청 완료: {movie} / {theater} / {screen or '-'}", "success")
        return redirect(url_for("open_alert_form"))      # PRG

    return render_template("alerts_open.html", title="오픈 알림 신청")

@app.route("/alerts/seat", methods=["GET", "POST"])
def seat_alert_form():
    if request.method == "POST":
        movie = request.form.get("movie", "").strip()
        theater = request.form.get("theater", "").strip()
        show_dt = request.form.get("show_datetime", "").strip()
        seats = request.form.get("desired_seats", "").strip()

        # 기본 유효성 검사
        if not movie or not theater or not show_dt or not seats:
            flash("모든 필드를 입력하세요.", "error")
            return redirect(url_for("seat_alert_form"))  # PRG

        # (다음 커밋에서 DB 저장 예정)
        flash(f"좌석 취소 알림 신청 완료: {movie} / {theater} / {show_dt} / {seats}", "success")
        return redirect(url_for("seat_alert_form"))      # PRG

    return render_template("alerts_seat.html", title="좌석 취소 알림 신청")

# --------------------------------------------------------

if __name__ == "__main__":
    app.run()  # 기본: http://127.0.0.1:5000
