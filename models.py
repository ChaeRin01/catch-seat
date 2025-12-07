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
    # ✅ 한국 로컬 시간(시스템 로컬 타임) 기준으로 저장
    created_at = db.Column(db.DateTime, default=datetime.now)

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
    # 개발 단계: NULL 허용 (나중에 nullable=False로 바꿀 수 있음)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    movie = db.Column(db.String(200), nullable=False, index=True)
    theater = db.Column(db.String(100), nullable=False, index=True)
    screen = db.Column(db.String(100))

    # 🔹 관람/상영 날짜 (예: "20251208" 형식)
    # 기존 데이터가 있어서 우선 nullable=True로 두고, 나중에 모두 채운 뒤 NOT NULL로 바꿀 수 있음.
    date = db.Column(db.String(8), index=True, nullable=True)

    # ✅ 알림 신청 시점도 한국 로컬 시간 기준으로 저장
    created_at = db.Column(db.DateTime, default=datetime.now)

    # 🔹 알림 상태 관리용 필드
    # 한 번이라도 메일 발송 완료되었는지
    is_sent = db.Column(db.Boolean, default=False, nullable=False)
    # 마지막으로 이 알림을 체크한 시각(크롤러/스케줄러용)
    last_checked = db.Column(db.DateTime)
    # 사용자가 알림을 끄면 False
    active = db.Column(db.Boolean, default=True, nullable=False)

    # 🔹 발송 쿨다운/중복 방지용 필드
    # 마지막으로 메일을 보낸 시각
    sent_at = db.Column(db.DateTime, nullable=True)
    # 지금까지 총 몇 번 보냈는지
    send_count = db.Column(db.Integer, default=0, nullable=False)
    # 발송 간 최소 간격(분 단위)
    cooldown_min = db.Column(db.Integer, default=30, nullable=False)

    def can_send_now(self, now=None):
        """
        이 알림에 대해 '지금' 메일을 보내도 되는지 판단하는 헬퍼.

        규칙:
        - active == False 면 발송 금지
        - is_sent == True 면(이미 최종 발송 완료 상태) 발송 금지
        - sent_at 이 있고, 마지막 발송 이후 cooldown_min 이 지나지 않았으면 발송 금지
        """
        if not self.active:
            return False
        if self.is_sent:
            return False

        if now is None:
            now = datetime.utcnow()

        # 아직 한 번도 보낸 적 없으면 바로 OK
        if self.sent_at is None:
            return True

        delta = now - self.sent_at
        return delta.total_seconds() >= self.cooldown_min * 60

    def __repr__(self) -> str:
        return f"<OpenAlert id={self.id} movie={self.movie} theater={self.theater}>"


# ----------- Alerts: Seat Cancel -----------
class SeatCancelAlert(db.Model):
    """
    좌석 취소 알림

    기본 아이디어:
    - 특정 상영 회차(brand + theater + show_datetime + movie [+ screen])에 대해
    - 사용자가 원하는 좌석 수(desired_count) 또는 좌석 리스트(desired_seats)를 등록
    - 등록 시점의 잔여좌석 수(baseline_available_seats)를 기준으로
      이후 잔여좌석 수가 baseline + desired_count 이상으로 증가하면 알림 발송.
    """
    __tablename__ = "seat_cancel_alerts"

    id = db.Column(db.Integer, primary_key=True)

    # 🔹 사용자
    # 개발 단계: NULL 허용 (나중에 nullable=False로 바꿀 수 있음)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    # 🔹 영화사 / 지점 / 상영 정보
    # 예: "MEGABOX", "CGV" 등 (현재는 메가박스 위주)
    brand = db.Column(db.String(20), nullable=False, default="MEGABOX", index=True)

    movie = db.Column(db.String(200), nullable=False, index=True)
    theater = db.Column(db.String(100), nullable=False, index=True)  # 지점 코드/ID
    screen = db.Column(db.String(100))                               # 상영관 이름/번호

    # 상영 일시(문자열 형태로 저장; 예: "2025-12-24 19:30")
    # 실제 크롤링/체크 로직에서 필요하면 "YYYYMMDD" + "HHMM" 으로 파싱해서 사용
    show_datetime = db.Column(db.String(40), nullable=False)

    # 🔹 사용자가 원하는 좌석 조건
    # 예: "E11,E12" (좌석 리스트) - 좌석 지정이 없는 경우도 있으니 옵션 처리
    desired_seats = db.Column(db.String(200), nullable=True)

    # 원하는 좌석 수 (예: 2 → "적어도 2자리 이상 다시 풀렸을 때")
    desired_count = db.Column(db.Integer, nullable=True)

    # ✅ 좌석 취소 알림 신청 시점 (한국 로컬 시간 기준)
    created_at = db.Column(db.DateTime, default=datetime.now)

    # 🔹 기준/최근 잔여좌석 수
    # 알림 등록 시점(또는 첫 체크 시점)의 잔여좌석 수
    baseline_available_seats = db.Column(db.Integer, nullable=True)

    # 마지막 체크 시점의 잔여좌석 수 (디버그/표시용)
    last_available_seats = db.Column(db.Integer, nullable=True)

    # 🔹 알림 상태 관리용 필드
    is_sent = db.Column(db.Boolean, default=False, nullable=False)
    last_checked = db.Column(db.DateTime)
    active = db.Column(db.Boolean, default=True, nullable=False)

    # 🔹 발송 쿨다운/중복 방지용 필드
    sent_at = db.Column(db.DateTime, nullable=True)
    send_count = db.Column(db.Integer, default=0, nullable=False)
    cooldown_min = db.Column(db.Integer, default=30, nullable=False)

    def can_send_now(self, now=None):
        """
        좌석 취소 알림에도 MovieOpenAlert과 동일한 기본 쿨다운 로직 사용.
        (필요하면 나중에 seat 전용 정책으로 커스터마이징 가능.)

        규칙:
        - active == False 면 발송 금지
        - is_sent == True 면(이미 최종 발송 완료 상태) 발송 금지
        - sent_at 이 있고, 마지막 발송 이후 cooldown_min 이 지나지 않았으면 발송 금지
        """
        if not self.active:
            return False
        if self.is_sent:
            return False

        if now is None:
            now = datetime.utcnow()

        if self.sent_at is None:
            return True

        delta = now - self.sent_at
        return delta.total_seconds() >= self.cooldown_min * 60

    def __repr__(self) -> str:
        return (
            f"<SeatAlert id={self.id} brand={self.brand} movie={self.movie} "
            f"theater={self.theater} show_datetime={self.show_datetime}>"
        )
