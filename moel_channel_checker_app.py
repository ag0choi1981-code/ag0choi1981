from __future__ import annotations

import csv
import io
import os
from datetime import datetime
from pathlib import Path

import streamlit as st

from youtube_minister_subscribers import load_ministers, resolve_channel_and_subscribers


def get_latest_moel_minister(ministers_json: Path) -> str:
    ministers = load_ministers(ministers_json)
    for rec in ministers:
        if rec.ministry == "고용노동부":
            return rec.minister
    return "김영훈"


def to_csv_bytes(rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["구분", "장관 이름", "채널명", "구독자 수", "조회시각"])
    for r in rows:
        writer.writerow([r["구분"], r["장관 이름"], r["채널명"], r["구독자 수"], r["조회시각"]])
    return buf.getvalue().encode("utf-8-sig")


def main() -> None:
    st.set_page_config(page_title="고용노동부 유튜브 구독자 조회", layout="centered")
    st.title("고용노동부 / 장관 유튜브 구독자 조회")
    st.caption("`조회` 버튼을 누를 때마다 최신 구독자 수를 다시 가져옵니다.")

    with st.sidebar:
        st.header("설정")
        ministers_json = st.text_input("장관명단 JSON 경로", value="ministries_2026.json")
        api_key = st.text_input(
            "YouTube API Key (선택)",
            value=os.getenv("YOUTUBE_API_KEY", ""),
            type="password",
            help="입력 시 YouTube Data API를 우선 사용합니다.",
        ).strip()

    check = st.button("조회", type="primary", use_container_width=True)
    if not check:
        st.info("`조회` 버튼을 눌러 최신 구독자 수를 확인하세요.")
        return

    with st.spinner("최신 구독자 수를 조회하는 중입니다..."):
        minister_name = get_latest_moel_minister(Path(ministers_json))
        checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        ministry_channel, ministry_subs = resolve_channel_and_subscribers(
            "고용노동부 공식 유튜브",
            api_key or None,
        )
        minister_channel, minister_subs = resolve_channel_and_subscribers(
            f"{minister_name} 고용노동부 장관 공식 유튜브",
            api_key or None,
        )

    rows = [
        {
            "구분": "고용노동부 공식 채널",
            "장관 이름": minister_name,
            "채널명": ministry_channel,
            "구독자 수": ministry_subs,
            "조회시각": checked_at,
        },
        {
            "구분": "고용노동부 장관 공식 채널",
            "장관 이름": minister_name,
            "채널명": minister_channel,
            "구독자 수": minister_subs,
            "조회시각": checked_at,
        },
    ]

    st.success("조회 완료")
    st.dataframe(rows, use_container_width=True, hide_index=True)

    st.download_button(
        label="CSV 다운로드",
        data=to_csv_bytes(rows),
        file_name=f"moel_subscribers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )

    if not api_key:
        st.warning(
            "API 키 없이 조회하면 HTML 파싱 폴백이 사용되며, 일부 경우 정확도가 떨어질 수 있습니다."
        )


if __name__ == "__main__":
    main()

