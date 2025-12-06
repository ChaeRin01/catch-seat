import smtplib
from email.mime.text import MIMEText
from flask import current_app

def send_email(to_email, subject, body):
    host = current_app.config.get("SMTP_HOST")
    port = current_app.config.get("SMTP_PORT")
    user = current_app.config.get("SMTP_USER")
    password = current_app.config.get("SMTP_PASSWORD")
    use_tls = current_app.config.get("SMTP_USE_TLS")
    default_sender = current_app.config.get("SMTP_DEFAULT_SENDER")

    # 필수 설정 체크
    if not host or not user or not password or not default_sender:
        raise ValueError(
            "SMTP 설정(SMTP_HOST / SMTP_USER / SMTP_PASSWORD / SMTP_DEFAULT_SENDER)이 누락되었습니다."
        )

    # MIME 메일 만들기
    msg = MIMEText(body, "html")
    msg["Subject"] = subject
    msg["From"] = default_sender
    msg["To"] = to_email

    # SMTP 연결
    server = smtplib.SMTP(host, port)
    if use_tls:
        server.starttls()

    # 로그인 후 발송
    server.login(user, password)
    server.sendmail(default_sender, [to_email], msg.as_string())
    server.quit()
