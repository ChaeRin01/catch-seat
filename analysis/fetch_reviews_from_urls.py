# analysis/fetch_reviews_from_urls.py

import os
import time
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

# 프로젝트 루트 기준 경로들
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
URL_DIR = os.path.join(BASE_DIR, "data", "urls")
REVIEW_DIR = os.path.join(BASE_DIR, "data", "seat_reviews")

# 간단한 User-Agent (크롤링 매너용)
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def load_urls_for_branch(branch_code: str) -> List[str]:
    """
    data/urls/{branch_code}.txt 파일에서 URL 목록을 읽어옵니다.
    - 빈 줄, #으로 시작하는 줄은 무시합니다.
    """
    path = os.path.join(URL_DIR, f"{branch_code}.txt")
    urls: List[str] = []

    if not os.path.isfile(path):
        print(f"[WARN] {branch_code}용 URL 파일이 없습니다: {path}")
        return urls

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                continue
            urls.append(line)

    return urls


def fetch_text_from_url(url: str, timeout: int = 10) -> str:
    """
    주어진 URL에서 HTML을 가져와서, 텍스트만 추출해서 반환합니다.
    - script, style, noscript 태그는 제거합니다.
    - 줄바꿈을 기준으로 어느 정도 읽기 좋게 만듭니다.
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

    # 빈 줄/공백 정리
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        lines.append(line)

    cleaned = "\n".join(lines)
    return cleaned


def save_review_text(branch_code: str, idx: int, text: str) -> None:
    """
    지점별 seat_reviews/{branch_code}/auto_{idx}.txt 파일로 저장합니다.
    """
    branch_dir = os.path.join(REVIEW_DIR, branch_code)
    os.makedirs(branch_dir, exist_ok=True)

    filename = f"auto_{idx:03d}.txt"
    path = os.path.join(branch_dir, filename)

    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"[SAVE] {branch_code} -> {filename} ({len(text)} chars)")


def main():
    if not os.path.isdir(URL_DIR):
        print(f"[ERROR] URL 디렉토리가 없습니다: {URL_DIR}")
        return

    os.makedirs(REVIEW_DIR, exist_ok=True)

    for branch_code, branch_name in MEGABOX_DOLBY_BRANCHES.items():
        print(f"\n[BRANCH] {branch_code} ({branch_name})")
        urls = load_urls_for_branch(branch_code)

        if not urls:
            print(f"[INFO] {branch_code}용 URL이 없습니다. 건너뜁니다.")
            continue

        for idx, url in enumerate(urls, start=1):
            print(f"  [FETCH] ({idx}/{len(urls)}) {url}")
            text = fetch_text_from_url(url)
            if not text:
                print("  [WARN] 내용이 비어 있습니다. 스킵합니다.")
                continue

            save_review_text(branch_code, idx, text)

            # 너무 빠르게 요청 보내지 않도록 살짝 쉬어주기 (매너)
            time.sleep(1.0)

    print("\n[DONE] 모든 URL 처리 완료.")


if __name__ == "__main__":
    main()
