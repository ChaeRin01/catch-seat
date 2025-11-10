# models.py
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

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
    show_datetime = db.Column(db.String(40), nullable=False)   # 스켈레톤: 문자열 사용
    desired_seats = db.Column(db.String(200), nullable=False)  # 예: "E11,E12"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
