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

if __name__=="__main__":
    app.run() #기본 http://127.0.0.1:5000