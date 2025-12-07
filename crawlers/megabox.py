from typing import List, Dict, Optional
import requests

# ─────────────────────────────────────
# DOLBY CINEMA 8개 지점 (brchNo 기준)
# ─────────────────────────────────────
# data-brch-no 값 = brchNo
# 버튼 텍스트 = brchNm
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


# ─────────────────────────────────────
# 메가박스 상영시간표 API (지점별 스케줄)
# ─────────────────────────────────────
MEGABOX_SCHEDULE_URL = "https://www.megabox.co.kr/on/oh/ohc/Brch/schedulePage.do"

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://www.megabox.co.kr",
        "Referer": "https://www.megabox.co.kr/theater",
    }
)


def _fetch_raw(branch_code: str, date_yyyymmdd: str) -> Dict:
    """
    메가박스 지점별 상영시간표 JSON 원본을 가져오는 내부 함수.

    branch_code : 메가박스 지점 코드 (brchNo, 예: "0052")
    date_yyyymmdd : 'YYYYMMDD'
    """
    brch_nm = MEGABOX_DOLBY_BRANCHES.get(branch_code)
    if not brch_nm:
        raise ValueError(f"[Megabox] 지원하지 않는 DOLBY 지점 코드입니다: {branch_code}")

    payload = {
        "brchNm": brch_nm,        # 지점 이름 (예: "수원AK플라자(수원역)")
        "brchNo": branch_code,    # 지점 코드
        "brchNo1": branch_code,   # 동일 코드 한 번 더
        "masterType": "brch",
        "playDe": date_yyyymmdd,  # 상영 날짜 (YYYYMMDD)
        "firstAt": "N",           # N이면 movieFormList만 옴 (날짜 리스트 생략)
    }

    resp = SESSION.post(MEGABOX_SCHEDULE_URL, data=payload, timeout=10)
    resp.raise_for_status()

    return resp.json()


def _format_seats(item: Dict) -> str:
    """
    schedulePage.do 응답(movieFormList 항목)에서
    좌석 상태를 우리 서비스용 문자열로 변환.

    - restSeatCnt == 0 이면 '매진'
    - 그 외에는 '잔여 N석'
    """
    rest = item.get("restSeatCnt")
    total = item.get("totSeatCnt")

    if rest is None:
        return ""

    if rest == 0:
        return "매진"

    return f"잔여 {rest}석"


def get_showtimes(branch_code: str, date_yyyymmdd: str) -> List[Dict]:
    """
    메가박스 상영정보 크롤링 (DOLBY CINEMA 전용)

    branch_code: 메가박스 지점 코드 (brchNo, 예: "0052" = 수원AK플라자(수원역))
    date_yyyymmdd: 'YYYYMMDD'

    반환 예시:
    [
      {
        "movie_title": "주토피아 2",
        "screen_name": "DOLBY CINEMA [Laser]",
        "start_time": "19:10",
        "seats_status": "잔여 214석",
        "bookable": True,  # 예매 가능 여부 (bokdAbleAt == "Y")
      },
      ...
    ]

    ❗ DOLBY 상영만 반환한다.
    """
    raw = _fetch_raw(branch_code, date_yyyymmdd)

    mega_map = raw.get("megaMap") or {}
    items = mega_map.get("movieFormList") or []

    showtimes: List[Dict] = []

    for item in items:
        # 상영관 이름
        screen_name = item.get("theabExpoNm") or item.get("theabEngNm") or ""

        # 🔹 DOLBY 상영만 필터링 (대소문자/공백 무시, 'dolby' 포함 여부)
        if "dolby" not in screen_name.lower():
            continue

        movie_title = item.get("rpstMovieNm") or item.get("movieNm") or ""
        start_time = item.get("playStartTime")  # "HH:MM" 또는 "HHMM"
        seats_status = _format_seats(item)
        bokd_able = item.get("bokdAbleAt") == "Y"  # 예매 가능 여부

        # HHMM -> HH:MM 보정
        if isinstance(start_time, str) and len(start_time) == 4 and ":" not in start_time:
            start_time = start_time[:2] + ":" + start_time[2:]

        showtimes.append(
            {
                "movie_title": movie_title,
                "screen_name": screen_name,
                "start_time": start_time,
                "seats_status": seats_status,
                "bookable": bokd_able,
            }
        )

    return showtimes


# ─────────────────────────────────────
# MovieOpenAlert 용 판별 로직
# ─────────────────────────────────────

def _normalize_text(s: Optional[str]) -> str:
    """영화 제목/상영관 비교용 단순 normalize"""
    if not s:
        return ""
    # 공백 제거 + 소문자
    return "".join(s.split()).lower()

def is_open_now(alert, showtimes: Optional[List[Dict]] = None) -> bool:
    """
    MovieOpenAlert 에 대한 '예매 오픈 여부' 판별.

    ❗ 영화 제목은 '정확히 일치하는 제목'이 아니라
       '사용자가 입력한 키워드가 포함된 제목'으로 판단한다.

    전제:
    - run-checks 쪽에서 같은 날짜/지점에 대해
      get_showtimes(alert.branch_code, alert.date)를 먼저 호출해서
      그 결과를 showtimes 인자로 넘겨주는 구조를 권장한다.

    매칭 조건:
    1) show['bookable'] 가 True (실제 예매 가능 상태)
    2) 영화 제목: alert 에 저장된 키워드가 상영 영화 제목에 '포함'되는지
       (공백 제거 + 소문자로 normalize 후 부분문자열 검사)
    3) alert 에 상영관(screen_name)이 지정되어 있다면,
       show['screen_name'] 안에 그 문자열(공백 제거/소문자)이 포함되는지 확인
    """
    if not showtimes:
        # v1: 호출자가 반드시 showtimes를 넘겨줘야 함
        return False

    # alert 에서 영화 키워드 / 상영관 이름을 뽑아오기
    # movie_keyword 필드를 따로 만들었다면 그걸 최우선으로 쓰고,
    # 없다면 movie_title 등에 들어있는 값을 키워드로 사용.
    keyword = (
        getattr(alert, "movie_keyword", None)
        or getattr(alert, "movie", None) 
        or getattr(alert, "movie_title", None)
        or getattr(alert, "movie_name", None)
        or getattr(alert, "title_ko", None)
        or getattr(alert, "title", None)
    )
    screen_pref = (
        getattr(alert, "screen_name", None)
        or getattr(alert, "screen", None)
        or getattr(alert, "theater_screen", None)
    )

    keyword_norm = _normalize_text(keyword)
    screen_norm = _normalize_text(screen_pref)

    if not keyword_norm:
        # 키워드가 없으면 판단 불가 → False
        return False

    for st in showtimes:
        if not st.get("bookable", False):
            # 아직 예매 안 열린 상영은 무시
            continue

        st_title_norm = _normalize_text(st.get("movie_title"))
        st_screen_norm = _normalize_text(st.get("screen_name"))

        # 1) 영화 제목: "키워드가 제목 안에 포함돼 있는지" 확인
        #    예: keyword="주토피아" → "주토피아2" / "주토피아 2" 모두 매칭
        if keyword_norm not in st_title_norm:
            continue

        # 2) 상영관이 선택된 경우: 부분일치 체크
        if screen_norm and screen_norm not in st_screen_norm:
            continue

        # → 여기까지 왔으면
        #    "내가 입력한 키워드가 포함된 영화"가
        #    이 지점/날짜/DOLBY 상영관에서 예매 오픈 상태라는 뜻
        return True

    return False


def check_movie_open_megabox_dolby(alert) -> bool:
    """
    실제 MovieOpenAlert 인스턴스를 받아서,
    - alert 가 메가박스 DOLBY 지점인지 확인하고
    - 해당 지점/날짜의 DOLBY 상영정보를 긁어온 뒤
    - is_open_now(alert, showtimes) 로 예매 오픈 여부를 반환한다.

    alert 에서 기대하는 필드 (여러 이름을 허용):
    - vendor       : "megabox" 여야 함
    - branch_code  : 메가박스 지점 코드 (brchNo, 예: "0052")
                     (없으면 theater_code, cinema_code 도 순서대로 시도)
    - date         : 'YYYYMMDD' 형식 문자열
                     (없으면 date_yyyymmdd, play_date 도 순서대로 시도)
    - movie_title / screen_name 은 is_open_now 내부에서 이미 처리
    """

    # 1) 벤더 체크
    vendor = getattr(alert, "vendor", None) or getattr(alert, "theater_vendor", None)
    if vendor and str(vendor).lower() != "megabox":
        # 메가박스가 아니면 여기서는 False (다른 크롤러에서 처리)
        return False

    # 2) 지점 코드(branch_code) 추출
    branch_code = (
        getattr(alert, "branch_code", None)
        or getattr(alert, "theater_code", None)
        or getattr(alert, "cinema_code", None)
    )
    if not branch_code:
        # 지점 코드 없으면 판단 불가
        return False

    branch_code = str(branch_code)

    # 3) 날짜(date_yyyymmdd) 추출
    date_yyyymmdd = (
        getattr(alert, "date", None)
        or getattr(alert, "date_yyyymmdd", None)
        or getattr(alert, "play_date", None)
    )
    if not date_yyyymmdd:
        return False

    date_yyyymmdd = str(date_yyyymmdd).replace("-", "")  # 혹시 YYYY-MM-DD 로 들어왔으면 제거

    # 4) DOLBY 8개 지점인지 확인
    if branch_code not in MEGABOX_DOLBY_BRANCHES:
        # 우리 DOLBY 타깃이 아닌 지점이면 여기서는 False
        return False

    # 5) 실제 상영정보 크롤링 후, is_open_now 로 판단
    try:
        showtimes = get_showtimes(branch_code, date_yyyymmdd)
    except Exception:
        # 네트워크/파싱 문제 등등은 일단 False 처리
        return False

    return is_open_now(alert, showtimes)


# ─────────────────────────────────────
# 로컬 테스트용 진입점
# ─────────────────────────────────────
if __name__ == "__main__":
    import datetime

    class DummyAlert:
        """테스트용 가짜 MovieOpenAlert"""

        def __init__(self, movie_title: str, screen_name: Optional[str] = None):
            self.movie_title = movie_title
            self.screen_name = screen_name

    # 예시: 수원AK플라자(수원역) DOLBY (0052) + 오늘 날짜
    branch_code = "0052"
    today = datetime.date.today().strftime("%Y%m%d")

    print(f"[Megabox DOLBY] branch_code={branch_code}, date={today}")

    showtimes = get_showtimes(branch_code, today)
    print(f"get_showtimes() → DOLBY 상영 {len(showtimes)}개")

    for st in showtimes[:10]:
        print(
            f"- {st['movie_title']} / {st['screen_name']} / "
            f"{st['start_time']} / {st['seats_status']} / bookable={st['bookable']}"
        )

    # 🔹 1) 영화 제목만으로 체크 (지점/날짜는 이미 showtimes 에 반영)
    alert1 = DummyAlert(movie_title="주토피아 2")
    print("\n[TEST] '주토피아 2' (상영관 무관) 예매 오픈 여부:",
          is_open_now(alert1, showtimes))

    # 🔹 2) 영화 + 상영관까지 지정
    alert2 = DummyAlert(movie_title="주토피아 2", screen_name="DOLBY CINEMA")
    print("[TEST] '주토피아 2' / 'DOLBY CINEMA' 예매 오픈 여부:",
          is_open_now(alert2, showtimes))

    # 🔹 3) 존재하지 않는 영화
    alert3 = DummyAlert(movie_title="없는 영화 제목")
    print("[TEST] '없는 영화 제목' 예매 오픈 여부:",
          is_open_now(alert3, showtimes))
    
    # 🔹 4) 실제 alert 형태로 한 번에 체크
    class DummyFullAlert:
        def __init__(self, movie_title, branch_code, date, screen_name=None):
            self.vendor = "megabox"
            self.movie_title = movie_title
            self.branch_code = branch_code
            self.date = date
            self.screen_name = screen_name

    fa = DummyFullAlert(
        movie_title="주토피아 2",
        branch_code=branch_code,
        date=today,
        screen_name="DOLBY CINEMA",
    )

    print("\n[TEST] DummyFullAlert → check_movie_open_megabox_dolby:",
          check_movie_open_megabox_dolby(fa))
