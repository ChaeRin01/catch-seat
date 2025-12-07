"""
CGV 상영 정보 크롤러 - 구현 불가
"""
import requests
from bs4 import BeautifulSoup

from typing import List, Dict, Any, Optional
from datetime import datetime


# CGV 극장 코드 매핑 (필요한 지점만 우선 추가)
THEATER_CODES: Dict[str, str] = {
    "용산아이파크몰": "0013",
    "강남": "0050",
    "홍대": "0056",
    # TODO: 필요하면 나중에 더 추가 가능
}

def get_showtimes(theater_code: str, date_yyyymmdd: str) -> List[Dict[str, Any]]:
    """
    CGV 상영정보 페이지를 요청하고,
    영화 제목 / 상영관 / 시작 시간을 파싱해서 리스트로 반환한다.

    반환 예시:
    [
        {
            "movie_title": "듄: 파트2",
            "screen_name": "IMAX관",
            "start_time": "19:00",
            "raw_time_text": "19:00"
        },
        ...
    ]
    """
    url = (
        "https://www.cgv.co.kr/common/showtimes/iframeTheater.aspx"
        f"?areacode=01&theatercode={theater_code}&date={date_yyyymmdd}"
    )

    try:
        # CGV가 직접 iframe URL 호출을 막는 경우가 있어 Referer 헤더를 함께 보냄
        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": f"https://www.cgv.co.kr/theater/?theaterCode={theater_code}&areacode=01",
            },
            timeout=10,
        )
        response.raise_for_status()
    except Exception as e:
        print("[CGV ERROR] 요청 실패:", e)
        return []


    soup = BeautifulSoup(response.text, "html.parser")

        # ▼ 디버깅: 받은 HTML 전체를 파일로 저장해 구조를 직접 확인하기
    debug_filename = f"debug_cgv_{theater_code}_{date_yyyymmdd}.html"
    try:
        with open(debug_filename, "w", encoding="utf-8") as f:
            f.write(response.text)
        print(f"[CGV DEBUG] HTML을 {debug_filename} 파일로 저장했습니다.")
    except Exception as e:
        print("[CGV ERROR] 디버그 HTML 저장 실패:", e)
        
    results: List[Dict[str, Any]] = []

    # 전체 상영정보 영역
    sect = soup.select_one("div.sect-showtimes")
    if not sect:
        print("[CGV DEBUG] sect-showtimes 영역을 찾지 못했습니다.")
        return results

    # 영화별 블록 (CGV 구조 기준: div.col-times 하나가 한 영화)
    movie_blocks = sect.select("div.col-times")

    for movie_block in movie_blocks:
        # 영화 제목
        title_tag = movie_block.select_one("div.info-movie strong")
        movie_title = title_tag.get_text(strip=True) if title_tag else "UNKNOWN"

        # 상영관/시간 정보가 들어있는 블록들 (div.type-hall)
        hall_blocks = movie_block.select("div.type-hall")

        for hall in hall_blocks:
            # 상영관 이름 (info-hall 안의 li 들 중 하나에 들어있음)
            screen_name = None
            hall_info_lis = hall.select("div.info-hall li")
            if hall_info_lis:
                # 여러 li가 있을 수 있지만, 일단 첫 번째 텍스트를 상영관 이름 비슷하게 사용
                screen_name = hall_info_lis[0].get_text(strip=True)

            # 시간 정보 (info-timetable 안의 li > a > em 등)
            time_items = hall.select("div.info-timetable li a")
            for t in time_items:
                # em 태그에 시작 시간이 보통 들어감 (예: "19:00")
                em = t.select_one("em")
                start_time = em.get_text(strip=True) if em else None

                raw_time_text = t.get_text(strip=True)

                results.append(
                    {
                        "movie_title": movie_title,
                        "screen_name": screen_name,
                        "start_time": start_time,
                        "raw_time_text": raw_time_text,
                    }
                )

    print(f"[CGV DEBUG] 파싱된 상영정보 개수: {len(results)}")
    return results


def is_open_now(alert, showtimes: Optional[List[Dict[str, Any]]] = None) -> bool:
    """
    MovieOpenAlert 인스턴스를 받아서,
    해당 영화가 해당 극장에서 해당 날짜에 '열려 있는지' 판단하는 함수.

    - alert.movie_title (또는 alert.movie)
    - alert.theater_name (또는 alert.theater)
    - alert.show_date / show_datetime

    등의 필드를 사용할 예정이며,
    실제 필드 이름은 models.MovieOpenAlert 정의를 보고 다음 단계에서 맞출 것이다.

    showtimes 파라미터:
        - 이미 get_showtimes()를 호출해 받은 결과가 있으면 재사용
        - None이면 내부에서 get_showtimes()를 다시 호출하도록 나중에 구현할 수 있음
    """
    # TODO: 다음 단계에서 alert / showtimes 구조에 맞춰 실제 비교 로직 구현
    #       (지금은 인터페이스만 고정)
    return False


def has_desired_seats(alert, showtimes: Optional[List[Dict[str, Any]]] = None) -> bool:
    """
    SeatCancelAlert 인스턴스를 받아서,
    '원하는 조건의 좌석이 있는지'를 판단하는 함수.

    Day 2에서는 좌석 정보를 실제로 보지 않고,
    - 나중에 좌석 정보 크롤링/연동을 할 수 있도록
      함수 인터페이스만 정의해 두는 MVP 단계이다.

    따라서 현재는 항상 False를 반환하게 둔다.
    추후 좌석 상태 크롤러가 준비되면 이 부분만 교체하면 된다.
    """
    # TODO: 이후 확장 시 좌석 데이터 연동
    return False
