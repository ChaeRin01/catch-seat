# analysis/auto_search_and_fetch_naver.py

import os
import time
import urllib.parse
from typing import Dict, List

import requests
from bs4 import BeautifulSoup

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

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
REVIEW_DIR = os.path.join(BASE_DIR, "data", "seat_reviews")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# 네이버 검색에서 건져올 웹페이지 URL 최대 개수
MAX_RESULTS_PER_BRANCH = 20

# 자동 수집 시 허용할 도메인 (필요하면 추가/삭제 가능)
ALLOWED_DOMAINS = [
    "blog.naver.com",
    "m.blog.naver.com",
    "tistory.com",
    "dcinside.com",
    "gall.dcinside.com",
]

# 지점 이름이 실제 본문에 어떻게 등장할 수 있는지, 패턴을 조금 넓게 정의
BRANCH_NAME_PATTERNS: Dict[str, List[str]] = {
    "0019": [
        "남양주현대아울렛스페이스원",
        "남양주 현대아울렛 스페이스원",
        "현대아울렛 스페이스원",
        "스페이스원 남양주",
        "메가박스 남양주",
    ],
    "7011": [
        "대구신세계",
        "대구 신세계",
        "동대구 메가박스",
        "메가박스 동대구",
        "대구신세계 메가박스",
    ],
    "0028": [
        "대전신세계아트앤사이언스",
        "대전신세계 아트앤사이언스",
        "아트앤사이언스 메가박스",
        "메가박스 대전신세계",
    ],
    "4062": [
        "송도(트리플스트리트)",
        "송도 트리플스트리트",
        "트리플스트리트",
        "메가박스 송도",
    ],
    "0052": [
        "수원AK플라자",
        "수원 AK플라자",
        "수원 AK 플라자",
        "수원역 메가박스",
        "메가박스 수원역",
    ],
    "0020": [
        "안성스타필드",
        "스타필드 안성",
        "메가박스 안성",
    ],
    "1351": [
        "코엑스",
        "메가박스 코엑스",
        "코엑스 메가박스",
        "코돌비",  # 커뮤니티 속어 가능성
    ],
    "4651": [
        "하남스타필드",
        "스타필드 하남",
        "메가박스 하남",
    ],
}


def build_query(branch_name: str) -> str:
    """
    지점 이름을 받아서 네이버 검색용 쿼리 문자열을 만듭니다.
    """
    # '돌비' 또는 '돌비시네마'를 쿼리에 포함해 좌석/관 관련 후기를 우선적으로 찾도록 함
    return f"메가박스 {branch_name} 돌비시네마 명당 좌석 후기"


def search_naver_web(query: str, max_results: int = MAX_RESULTS_PER_BRANCH) -> List[str]:
    """
    네이버 웹 검색 결과에서 상위 max_results개의 URL을 가져옵니다.
    (실제 서비스에서는 약관/robots.txt를 반드시 확인해야 합니다.)
    """
    base_url = "https://search.naver.com/search.naver"
    params = {
        "where": "web",
        "sm": "tab_jum",
        "query": query,
    }

    try:
        resp = requests.get(base_url, params=params, headers=DEFAULT_HEADERS, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"[ERROR] 네이버 검색 실패: {query} ({e})")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results: List[str] = []
    seen = set()

    # a 태그 중에서 href가 있고, 허용 도메인에 해당하는 것만 사용
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"):
            continue

        parsed = urllib.parse.urlparse(href)
        host = parsed.netloc.lower()

        if not any(host.endswith(domain) for domain in ALLOWED_DOMAINS):
            continue

        # URL 중복 제거
        if href in seen:
            continue
        seen.add(href)
        results.append(href)

        if len(results) >= max_results:
            break

    return results


def fetch_text_from_url(url: str, timeout: int = 10) -> str:
    """
    주어진 URL에서 HTML을 가져와 텍스트만 추출합니다.
    """
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
        resp.raise_for_status()
    except Exception as e:
        print(f"[ERROR] 요청 실패: {url} ({e})")
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")

    # script, style, noscript 제거
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text("\n")

    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        lines.append(line)

    cleaned = "\n".join(lines)
    return cleaned


def save_review_text(branch_code: str, idx: int, text: str, source: str) -> None:
    """
    지점별 seat_reviews/{branch_code}/auto_search_naver_{idx}.txt 파일로 저장합니다.
    파일 상단에 출처 URL을 주석처럼 남겨둡니다.
    """
    branch_dir = os.path.join(REVIEW_DIR, branch_code)
    os.makedirs(branch_dir, exist_ok=True)

    filename = f"auto_search_naver_{idx:03d}.txt"
    path = os.path.join(branch_dir, filename)

    header = f"# SOURCE: {source}\n\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(header)
        f.write(text)

    print(f"[SAVE] {branch_code} -> {filename} ({len(text)} chars)")


def text_matches_branch(branch_code: str, text: str) -> bool:
    """
    본문 텍스트 안에 해당 지점을 가리키는 표현이 실제로 포함되어 있는지 확인합니다.
    지점별로 여러 패턴(예: '스타필드 하남', '메가박스 하남' 등)을 허용합니다.
    """
    patterns = BRANCH_NAME_PATTERNS.get(branch_code)
    if not patterns:
        # 패턴 정보가 없으면 일단 통과시키거나, 보수적으로 False로 둘 수 있음.
        # 여기서는 일단 통과시키도록 함.
        return True

    return any(p in text for p in patterns)


def main():
    os.makedirs(REVIEW_DIR, exist_ok=True)

    for branch_code, branch_name in MEGABOX_DOLBY_BRANCHES.items():
        query = build_query(branch_name)
        print(f"\n[BRANCH] {branch_code} ({branch_name})")
        print(f"  [QUERY] {query}")

        urls = search_naver_web(query, max_results=MAX_RESULTS_PER_BRANCH)
        if not urls:
            print("  [INFO] 검색 결과 없음 또는 필터링됨.")
            continue

        print(f"  [INFO] {len(urls)}개 URL 수집됨.")

        saved_count = 0

        for idx, url in enumerate(urls, start=1):
            print(f"    [FETCH] ({idx}/{len(urls)}) {url}")
            text = fetch_text_from_url(url)
            if not text:
                print("    [WARN] 내용이 비어 있음. 스킵.")
                continue

            # 페이지 안에 지점 이름 관련 패턴이 실제로 포함되어 있는지 확인
            if not text_matches_branch(branch_code, text):
                print(f"    [SKIP] 본문에 지점 관련 패턴이 없음. 스킵.")
                continue

            saved_count += 1
            save_review_text(branch_code, saved_count, text, source=url)

            # 너무 빠르게 요청 보내지 않기 위해 잠깐 쉬기
            time.sleep(1.0)

        print(f"  [DONE] {branch_code} ({branch_name}) => 저장된 문서: {saved_count}개")

    print("\n[ALL DONE] 네이버 자동 검색 + 크롤링 완료. 이제 seat_popularity.py를 실행해보세요.")


if __name__ == "__main__":
    main()
