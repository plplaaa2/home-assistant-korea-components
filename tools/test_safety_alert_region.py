"""Live check for the Safety Alert region endpoints.

This is an opt-in network test for the current Safe Korea region API.
"""

from __future__ import annotations

import json

import requests


BASE_URL = "https://www.safekorea.go.kr/safekorea-kor/ctim/cmsg"
HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://www.safekorea.go.kr",
    "Referer": "https://www.safekorea.go.kr/safekorea-kor/ctim/cmsg/calamitySms.do",
}


def request(session, endpoint: str, payload: dict) -> None:
    response = session.post(
        f"{BASE_URL}/{endpoint}",
        json=payload,
        headers=HEADERS,
        verify=False,
        timeout=15,
    )
    print(f"{endpoint}: HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError:
        print(response.text[:500])
        return
    print(json.dumps(data[:5] if isinstance(data, list) else data, ensure_ascii=False, indent=2))
    if isinstance(data, list):
        print(f"총 {len(data)}건")


if __name__ == "__main__":
    with requests.Session() as session:
        request(session, "changeSidoList_new.do", {"sbLawArea1": "1100000000"})
        request(
            session,
            "changeSggList_new.do",
            {"sbLawArea1": "1100000000", "sbLawArea2": "1138000000"},
        )
