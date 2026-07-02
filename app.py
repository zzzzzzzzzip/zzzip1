import streamlit as st
import io
import os
import re
from ebooklib import epub

# 웹페이지 기본 설정 (스마트폰 해상도 대응)
st.set_page_config(page_title="TXT to EPUB 변환기", page_icon="📚", layout="centered")

st.title("📚 TXT ➔ EPUB 웹 변환기")
st.write("스마트폰에서도 간편하게 텍스트를 전자책으로 변환하세요!")

# --- 1. 파일 업로드 구역 ---
st.subheader("1. 파일 업로드")
uploaded_file = st.file_uploader("텍스트 파일 (*.txt) 선택", type=["txt"])
cover_file = st.file_uploader("표지 이미지 (*.jpg, *.png) 선택 (선택사항)", type=["jpg", "jpeg", "png"])

# --- 2. 책 정보 설정 ---
st.subheader("2. 도서 정보 입력")
default_title = os.path.splitext(uploaded_file.name)[0] if uploaded_file else ""
title = st.text_input("도서명", value=default_title)
author = st.text_input("작가명", value="작자미상")

# --- 3. 목차 설정 구역 ---
st.subheader("3. 목차 자동 구분 기준")
toc_mode = st.radio("설정 방식 선택", ["제공되는 양식에서 선택", "내가 직접 기준 단어 지정"], horizontal=True)

if toc_mode == "제공되는 양식에서 선택":
    preset = st.selectbox(
        "양식 선택",
        ["#001, #002 형태 (샵+숫자)", "제 1화, 제 2장 형태", "Chapter 1, Chapter 2 형태", "1., 2., 3. 형태"]
    )
    if "#001" in preset: 
        toc_pattern = r"^#\s*\d+"
    elif "제 1화" in preset: 
        toc_pattern = r"^제\s*\d+\s*[화|장|편]"
    elif "Chapter" in preset: 
        toc_pattern = r"^Chapter\s*\d+"
    else: 
        toc_pattern = r"^\d+\."
else:
    custom_word = st.text_input("기준 단어 입력", value="화")
    if custom_word:
        escaped_word = re.escape(custom_word)
        toc_pattern = rf".*\d+\s*{escaped_word}"
    else:
        toc_pattern = None

st.info("💡 팁: 제목 뒤에 숫자가 붙는 소설은 [내가 직접 기준 단어 지정]을 누르고 '화'를 입력하시면 정확하게 장이 분리됩니다!")
st.caption("※ 들여쓰기는 문단 맨 앞에 1글자 크기(1em)로 자동 적용됩니다.")

# --- 4. 변환 및 다운로드 기능 ---
if uploaded_file and title and author:
    if toc_mode == "내가 직접 기준 단어 지정" and not toc_pattern:
        st.warning("직접 입력 칸에 기준 단어를 적어주세요.")
    else:
        st.markdown("---")
        if st.button("🚀 EPUB 변환하기", use_container_width=True):
            try:
                raw_bytes = uploaded_file.read()
                txt_content = None
                
                encodings = ["utf-8-sig", "utf-8", "cp949", "utf-16", "euc-kr"]
                for enc in encodings:
                    try:
                        txt_content = raw_bytes.decode(
