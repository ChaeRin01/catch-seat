# analysis/seat_popularity.py

import os
import re
import json
from collections import Counter
from typing import Dict, List

# --- DOLBY 8개 지점 고정 상수 ---
MEGABOX_DOLBY_BRANCHES: Dict[str, str] = {
    "0019": "남양주현대아울렛스페이스원",
    "7011": "대구신세계(동대구)",
    "0028": "대전신세계아트앤사이언스",
    "4062": "송도(트리플스트리트)",
    "0052": "수원AK플라자(수원역)",
    "0020": "안성스타필드",
    "1351": "코엑스",
    "4651": "하남스타필드",
}

# --- 지점별 실제 좌석 레이아웃 ---
# 행(row): 'A'부터 max_row까지, 번호(seat): 1부터 max_seat까지가 유효
BRANCH_SEAT_LAYOUT: Dict[str, Dict[str, object]] = {
    "0019": {"max_row": "M", "max_seat": 24},  # 남양주
    "7011": {"max_row": "J", "max_seat": 22},  # 대구
    "0028": {"max_row": "M", "max_seat": 26},  # 대전
    "4062": {"max_row": "L", "max_seat": 25},  # 송도
    "0052": {"max_row": "M", "max_seat": 23},  # 수원
    "0020": {"max_row": "O", "max_seat": 19},  # 안성
    "1351": {"max_row": "R", "max_seat": 24},  # 코엑스
    "4651": {"max_row": "L", "max_seat": 29},  # 하남
}

# 프로젝트 루트 기준으로 data 디렉토리 설정
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
DATA_DIR = os.path.join(BASE_DIR, "data", "seat_reviews")

# --- 좌석/열 패턴 정규식들 ---

# E10, F8, C12 ...
PATTERN_SIMPLE = re.compile(r"\b([A-Z])[ ]?([0-9]{1,2})\b")

# E열 10번, F열 8번 ...
PATTERN_KOR = re.compile(r"\b([A-Z])\s*열\s*([0-9]{1,2})\s*번?")

# E열 10-12, F열 8~10 ...
PATTERN_RANGE = re.compile(r"\b([A-Z])\s*열\s*([0-9]{1,2})\s*[-~]\s*([0-9]{1,2})")

# G,H,I,J열의 11번부터 19번 좌석
PATTERN_ROW_LIST_NUM_RANGE = re.compile(
    r"\b([A-Z](?:,[A-Z]){1,})\s*열의\s*([0-9]{1,2})번부터\s*([0-9]{1,2})번"
)

# F~K열 (알파벳 범위)
PATTERN_ROW_ALPHA_RANGE = re.compile(r"\b([A-Z])\s*[~\-]\s*([A-Z])\s*열")

# H I열 / H, I열 (두 개 정도를 같이 말하는 표현)
PATTERN_ROW_PAIR = re.compile(r"\b([A-Z])\s*[ ,/]\s*([A-Z])\s*열")

# G열 처럼 열만 말한 경우
PATTERN_ROW_ONLY = re.compile(r"\b([A-Z])\s*열\b")


def extract_seat_mentions(text: str) -> List[str]:
    """
    텍스트에서 좌석/열 언급을 찾아 'E10', 'F8' 같은 형태로 리스트 반환.
    열만 언급된 경우에는 해당 열의 임의 좌석(예: 1번)로 치환해서
    '행 인기'와 '존 인기'에 반영되도록 한다.
    """
    # 대소문자 섞여 있을 수 있으니 미리 대문자로 변환해서 처리
    text_up = text.upper()
    seats: List[str] = []

    # 0) G,H,I,J열의 11번부터 19번 좌석
    for rows_str, start, end in PATTERN_ROW_LIST_NUM_RANGE.findall(text_up):
        try:
            s = int(start)
            e = int(end)
        except ValueError:
            continue
        if s > e:
            s, e = e, s
        rows = [r.strip() for r in rows_str.split(",") if r.strip()]
        for row in rows:
            for num in range(s, e + 1):
                seats.append(f"{row}{num}")

    # 1) F~K열 같은 알파벳 범위 → 각 열에 대해 대표 좌석(1번)으로 환산
    for start_row, end_row in PATTERN_ROW_ALPHA_RANGE.findall(text_up):
        s_ord = ord(start_row)
        e_ord = ord(end_row)
        if s_ord > e_ord:
            s_ord, e_ord = e_ord, s_ord
        for code in range(s_ord, e_ord + 1):
            r = chr(code)
            seats.append(f"{r}1")

    # 2) H I열 / H, I열 같은 2개 열 언급 → 각 열에 대해 대표 좌석(1번)
    for r1, r2 in PATTERN_ROW_PAIR.findall(text_up):
        seats.append(f"{r1}1")
        seats.append(f"{r2}1")

    # 3) G열 처럼 열만 말한 경우 → 해당 열의 대표 좌석(1번)
    for row in PATTERN_ROW_ONLY.findall(text_up):
        seats.append(f"{row}1")

    # 4) E열 8~12, F열 10-12 같은 범위 표현 (열 하나 + 번호 범위)
    for row, start, end in PATTERN_RANGE.findall(text_up):
        try:
            s = int(start)
            e = int(end)
        except ValueError:
            continue
        if s > e:
            s, e = e, s
        for num in range(s, e + 1):
            seats.append(f"{row}{num}")

    # 5) E열 10번, F열 8번 ...
    for row, num in PATTERN_KOR.findall(text_up):
        try:
            n = int(num)
        except ValueError:
            continue
        seats.append(f"{row}{n}")

    # 6) E10, F8, C12 ...
    for row, num in PATTERN_SIMPLE.findall(text_up):
        try:
            n = int(num)
        except ValueError:
            continue
        seats.append(f"{row}{n}")

    return seats


def is_valid_seat(branch_code: str, seat: str) -> bool:
    """
    해당 지점(branch_code)에 실제 존재 가능한 좌석인지 검사.
    seat 예시: 'E10', 'Q1'
    """
    layout = BRANCH_SEAT_LAYOUT.get(branch_code)
    if layout is None:
        # 레이아웃 정보 없으면 일단 모두 허용
        return True

    if not seat:
        return False

    row = seat[0].upper()
    num_part = seat[1:]

    try:
        num = int(num_part)
    except ValueError:
        return False

    max_row = str(layout["max_row"]).upper()
    max_seat = int(layout["max_seat"])

    # 'A' <= row <= max_row
    if not ("A" <= row <= max_row):
        return False

    if not (1 <= num <= max_seat):
        return False

    return True


def analyze_branch(branch_code: str) -> Counter:
    """
    한 지점(브랜치 코드) 디렉토리 내 모든 텍스트 파일을 읽어 좌석 빈도 Counter 반환.
    지점별 좌석 레이아웃(BRANCH_SEAT_LAYOUT)에 맞지 않는 좌석은 버린다.
    """
    branch_dir = os.path.join(DATA_DIR, branch_code)
    seat_counter: Counter = Counter()

    if not os.path.isdir(branch_dir):
        print(f"[WARN] 지점 {branch_code} 디렉토리가 없습니다: {branch_dir}")
        return seat_counter

    for filename in os.listdir(branch_dir):
        if not filename.endswith(".txt"):
            continue
        path = os.path.join(branch_dir, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except UnicodeDecodeError:
            print(f"[WARN] 인코딩 문제로 스킵: {path}")
            continue

        raw_seats = extract_seat_mentions(text)

        # 지점별 유효 좌석만 필터링
        seats = [s for s in raw_seats if is_valid_seat(branch_code, s)]

        seat_counter.update(seats)

    return seat_counter


def build_zone_summary(seat_counter: Counter) -> Dict[str, float]:
    """
    좌석 단위 Counter를 바탕으로 열(행) 구간별 비율 요약.
    A-B, C-D, E-F, G-H, I-J, K-L, M-N, O-P, Q-R 이렇게 2열씩 묶어서 본다.
    """
    total = sum(seat_counter.values()) or 1

    row_counter: Counter = Counter()
    for seat, cnt in seat_counter.items():
        if not seat:
            continue
        row = seat[0].upper()  # 'E10' -> 'E'
        row_counter[row] += cnt

    # 2열 단위 구간 정의
    zone_groups = [
        ("A-B열", {"A", "B"}),
        ("C-D열", {"C", "D"}),
        ("E-F열", {"E", "F"}),
        ("G-H열", {"G", "H"}),
        ("I-J열", {"I", "J"}),
        ("K-L열", {"K", "L"}),
        ("M-N열", {"M", "N"}),
        ("O-P열", {"O", "P"}),
        ("Q-R열", {"Q", "R"}),
    ]

    zones: Dict[str, float] = {}
    for label, rows in zone_groups:
        score = sum(cnt for r, cnt in row_counter.items() if r in rows) / total
        zones[label] = score

    return zones


def main():
    if not os.path.isdir(DATA_DIR):
        print(f"[ERROR] 데이터 디렉토리가 없습니다: {DATA_DIR}")
        return

    result = {}

    for branch_code, branch_name in MEGABOX_DOLBY_BRANCHES.items():
        print(f"[INFO] 분석 중: {branch_code} ({branch_name})")
        seat_counter = analyze_branch(branch_code)

        total_mentions = int(sum(seat_counter.values()))
        top_seats = seat_counter.most_common(20)
        zones = build_zone_summary(seat_counter)

        result[branch_code] = {
            "branch_name": branch_name,
            "total_mentions": total_mentions,
            "top_seats": [
                {"seat": seat, "count": int(cnt)}
                for seat, cnt in top_seats
            ],
            "zones": [
                {"label": label, "score": float(score)}
                for label, score in zones.items()
            ],
        }

    output_dir = os.path.join(BASE_DIR, "data")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "seat_popularity.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[DONE] 결과 저장: {output_path}")


if __name__ == "__main__":
    main()
