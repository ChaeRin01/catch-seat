# models.py
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin  # ← 추가

db = SQLAlchemy()

class User(db.Model, UserMixin):    # ← UserMixin 상속
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, pw: str):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw: str) -> bool:
        return check_password_hash(self.password_hash, pw)

class MovieOpenAlert(db.Model):
    __tablename__ = "movie_open_alerts"
    id = db.Column(db.Integer, primary_key=True)
    movie = db.Column(db.String(200), nullable=False)
    theater = db.Column(db.String(100), nullable=False)
    screen = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SeatCancelAlert(db.Model):
    __tablename__ = "seat_cancel_alerts"
    id = db.Column(db.Integer, primary_key=True)
    movie = db.Column(db.String(200), nullable=False)
    theater = db.Column(db.String(100), nullable=False)
    show_datetime = db.Column(db.String(40), nullable=False)
    desired_seats = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
