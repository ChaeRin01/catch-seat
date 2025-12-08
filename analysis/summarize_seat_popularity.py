# analysis/summarize_seat_popularity.py

import os
import json
from typing import Dict, List

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
DATA_PATH = os.path.join(BASE_DIR, "data", "seat_popularity.json")


def load_data() -> Dict[str, dict]:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def make_zone_summary(zones: List[Dict[str, object]]) -> str:
    """
    zones 리스트를 받아서
    "G-H열이 가장 인기, I-J열이 그 다음" 같은 서술을 만든다.
    """
    if not zones:
        return "열(행) 구간별로 뚜렷한 패턴을 찾기 어렵습니다."

    # score 기준 내림차순 정렬
    sorted_zones = sorted(zones, key=lambda z: z["score"], reverse=True)

    # score > 0인 것만 사용
    top = [z for z in sorted_zones if z["score"] > 0]
    if not top:
        return "열(행) 구간별로 뚜렷한 패턴을 찾기 어렵습니다."

    top1 = top[0]
    msg_parts = []

    # 강도에 따라 문구 조금 다르게
    if top1["score"] >= 0.5:
        msg_parts.append(f"{top1['label']} 구간이 압도적으로 많이 언급되는 핵심 명당 구역입니다.")
    elif top1["score"] >= 0.3:
        msg_parts.append(f"{top1['label']} 구간이 가장 많이 언급되는 주요 명당 구역입니다.")
    else:
        msg_parts.append(f"{top1['label']} 구간이 상대적으로 더 많이 언급되는 편입니다.")

    if len(top) >= 2:
        top2 = top[1]
        if top2["score"] >= 0.15:
            msg_parts.append(f"{top2['label']} 구간도 비교적 선호되는 구역입니다.")

    if len(top) >= 3:
        top3 = top[2]
        if top3["score"] >= 0.1:
            msg_parts.append(f"{top3['label']} 구간은 호불호가 있지만 후기에서 자주 언급되는 편입니다.")

    return " ".join(msg_parts)


def summarize_branch(code: str, data: Dict[str, dict]) -> Dict[str, str]:
    """
    한 지점 코드에 대한 '인기 구역' 요약 텍스트만 리턴.
    """
    entry = data.get(code)
    if not entry:
        return {
            "branch_name": MEGABOX_DOLBY_BRANCHES.get(code, code),
            "zone_summary": "데이터가 없습니다.",
        }

    zone_summary = make_zone_summary(entry.get("zones", []))

    return {
        "branch_name": entry.get("branch_name", MEGABOX_DOLBY_BRANCHES.get(code, code)),
        "zone_summary": zone_summary,
    }


def main():
    if not os.path.exists(DATA_PATH):
        print(f"[ERROR] seat_popularity.json이 존재하지 않습니다: {DATA_PATH}")
        return

    data = load_data()

    for code in sorted(MEGABOX_DOLBY_BRANCHES.keys()):
        summary = summarize_branch(code, data)
        print("=" * 60)
        print(f"[{code}] {summary['branch_name']}")
        print(f"- 인기 구역 요약: {summary['zone_summary']}")


if __name__ == "__main__":
    main()
