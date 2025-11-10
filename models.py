# models.py
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# ----------- User -----------
class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 관계(역참조)
    open_alerts = db.relationship("MovieOpenAlert", backref="user", lazy=True)
    seat_alerts = db.relationship("SeatCancelAlert", backref="user", lazy=True)

    # 비밀번호 유틸
    def set_password(self, pw: str) -> None:
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw: str) -> bool:
        return check_password_hash(self.password_hash, pw)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"

# ----------- Alerts: Movie Open -----------
class MovieOpenAlert(db.Model):
    __tablename__ = "movie_open_alerts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))  # 로그인 사용자 연결(개발 단계: NULL 허용)
    movie = db.Column(db.String(200), nullable=False, index=True)
    theater = db.Column(db.String(100), nullable=False, index=True)
    screen = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<OpenAlert id={self.id} movie={self.movie} theater={self.theater}>"

# ----------- Alerts: Seat Cancel -----------
class SeatCancelAlert(db.Model):
    __tablename__ = "seat_cancel_alerts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))  # 로그인 사용자 연결(개발 단계: NULL 허용)
    movie = db.Column(db.String(200), nullable=False, index=True)
    theater = db.Column(db.String(100), nullable=False, index=True)
    show_datetime = db.Column(db.String(40), nullable=False)    # 스켈레톤: 문자열
    desired_seats = db.Column(db.String(200), nullable=False)   # 예: "E11,E12"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<SeatAlert id={self.id} movie={self.movie} {self.show_datetime}>"
