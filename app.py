from flask import Flask, render_template

app = Flask(__name__)

@app.get("/")
def index():
    return "Hello, Flask!"

@app.get("/home")
def home():
    return render_template("home.html", title="홈")

@app.get("/hw1")
def hw1():
    return render_template("hw1.html")

@app.get("/select")
def select_service():
    return render_template("service_select.html", title="서비스 선택")

@app.get("/alerts/open")
def open_alert_form():
    return render_template("alerts_open.html", title="오픈 알림 신청")

@app.get("/alerts/seat")
def seat_alert_form():
    return render_template("alerts_seat.html", title="좌석 취소 알림 신청")

if __name__=="__main__":
    app.run() #기본 http://127.0.0.1:5000