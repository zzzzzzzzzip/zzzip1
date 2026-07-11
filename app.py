import streamlit as st
import io
import os
import re
from ebooklib import epub
from bs4 import BeautifulSoup

# 웹페이지 기본 설정 (스마트폰 해상도 대응)
st.set_page_config(page_title="통합 EPUB 변환기", page_icon="📚", layout="centered")

st.title("📚 TXT / EPUB 통합 변환기")
st.write("텍스트 파일이나 기존 이펍을 내 커스텀 스타일로 완벽하게 재가공하세요!")

# --- 1. 파일 업로드 구역 ---
st.subheader("1. 파일 업로드")
uploaded_file = st.file_uploader("파일 선택 (*.txt, *.epub)", type=["txt", "epub"])
cover_file = st.file_uploader("표지 이미지 (*.jpg, *.png) 선택 (선택사항)", type=["jpg", "jpeg", "png"])

# --- 2. 책 정보 설정 ---
st.subheader("2. 도서 정보 입력")
default_title = os.path.splitext(uploaded_file.name)[0] if uploaded_file else ""
title = st.text_input("도서명", value=default_title)
author = st.text_input("작가명", value="작자미상")

# --- 3. 목차 설정 구역 ---
st.subheader("3. 목차 자동 구분 기준 (TXT 파일 전용)")
toc_mode = st.radio("설정 방식 선택", ["제공되는 양식에서 선택", "내가 직접 기준 단어 지정"], horizontal=True)

if toc_mode == "제공되는 양식에서 선택":
    preset = st.selectbox(
        "양식 선택",
        ["#001, #002 형태 (샵+숫자)", "제 1화, 제 2장 형태", "Chapter 1, Chapter 2 형태", "1., 2., 3. 형태"]
    )
    if "#001" in preset: 
        toc_pattern = r"#\s*\d+.*"
    elif "제 1화" in preset: 
        toc_pattern = r"제\s*\d+\s*[화|장|편].*"
    elif "Chapter" in preset: 
        toc_pattern = r"Chapter\s*\d+.*"
    else: 
        toc_pattern = r"\d+\..*"
else:
    custom_word = st.text_input("기준 단어 입력", value="화")
    if custom_word:
        escaped_word = re.escape(custom_word)
        toc_pattern = rf"\d+\s*{escaped_word}.*"
    else:
        toc_pattern = None

st.markdown("**목차 텍스트 정제 설정 (TXT 파일 전용)**")
clean_title_option = st.checkbox("목차에서 공통 소설 제목 제외하기 (화수와 소제목만 남기기)", value=True)

# 다음 줄 소제목 설정 구역
sub_title_option = st.checkbox("화수 제목 다음 줄을 소제목으로 인식하여 효과 적용하기", value=False)

# [신규 기능] 목차 연결 선택 옵션 체크박스 추가
join_title_option = st.checkbox("➔ 선택사항: 목차(화수) 뒤에 소제목을 이어서 표시하기", value=False, disabled=not sub_title_option)

st.info("💡 팁: 기존에 갖고 있던 EPUB 파일을 업로드하면 목차 구분 설정을 건드릴 필요 없이, 내 커스텀 스타일(화 제목 여백, 크기, * * * 가운데 정렬 및 줄바꿈)만 똑같이 입혀서 새로 내려받아 줍니다!")
st.caption("※ 들여쓰기는 문단 맨 앞에 1글자 크기(1em)로 자동 적용됩니다.")

# --- 4. 변환 및 다운로드 기능 ---
if uploaded_file and title and author:
    if uploaded_file.name.endswith(".txt") and toc_mode == "내가 직접 기준 단어 지정" and not toc_pattern:
        st.warning("직접 입력 칸에 기준 단어를 적어주세요.")
    else:
        st.markdown("---")
        if st.button("🚀 커스텀 스타일로 변환하기", use_container_width=True):
            try:
                chapters = []
                is_epub = uploaded_file.name.endswith(".epub")

                if is_epub:
                    # --- 기존 EPUB 파일 파싱 구역 ---
                    epub_stream = io.BytesIO(uploaded_file.read())
                    input_book = epub.read_epub(epub_stream)
                    
                    for item in input_book.get_items():
                        if item.get_type() == 9: 
                            soup = BeautifulSoup(item.get_content(), "html.parser")
                            h_tag = soup.find(["h1", "h2", "h3"])
                            ch_title = h_tag.get_text().strip() if h_tag else "본문"
                            
                            ch_lines = []
                            for p in soup.find_all("p"):
                                p_text = p.get_text().strip()
                                if p_text:
                                    ch_lines.append(p_text)
                            
                            if ch_lines:
                                if ch_lines[0] == ch_title:
                                    ch_lines.pop(0)
                                if ch_lines:
                                    chapters.append((ch_title, None, ch_lines))
                else:
                    # --- 기존 TXT 파일 파싱 구역 ---
                    raw_bytes = uploaded_file.read()
                    txt_content = None
                    encodings = ["utf-8-sig", "utf-8", "cp949", "utf-16", "euc-kr"]
                    for enc in encodings:
                        try:
                            txt_content = raw_bytes.decode(enc)
                            break
                        except UnicodeDecodeError:
                            continue
                    if txt_content is None:
                        txt_content = raw_bytes.decode("utf-8", errors="ignore")

                    lines = txt_content.splitlines()
                    current_chapter_title = "프롤로그"
                    current_sub_title = None
                    current_chapter_lines = []
                    compiled_pattern = re.compile(toc_pattern)

                    for line in lines:
                        line = line.strip()
                        if not line: 
                        
                            continue
                        
                        match = compiled_pattern.search(line)
                        if match:
                            if current_chapter_lines or current_sub_title:
                                chapters.append((current_chapter_title, current_sub_title, current_chapter_lines))
                                current_chapter_lines = []
                                current_sub_title = None
                            
                            extracted_title = match.group().strip()
                            if clean_title_option:
                                current_chapter_title = extracted_title
                            else:
                                current_chapter_title = line
                        else:
                            if sub_title_option and not current_chapter_lines and current_sub_title is None and current_chapter_title != "프롤로그":
                                current_sub_title = line
                            else:
                                current_chapter_lines.append(line)
                            
                    if current_chapter_lines or current_sub_title:
                        chapters.append((current_chapter_title, current_sub_title, current_chapter_lines))

                # --- 공통: 내 커스텀 규칙대로 새 EPUB 빌드 구역 ---
                book = epub.EpubBook()
                book.set_identifier('web_generated_id_12345')
                book.set_title(title)
                book.set_language('ko')
                book.add_author(author)

                if cover_file:
                    book.set_cover("cover.jpg", cover_file.read())
                elif is_epub:
                    for item in input_book.get_items():
                        if item.get_type() == 4: 
                            if "cover" in item.get_name().lower():
                                book.set_cover("cover.jpg", item.get_content())
                                break

                # [개선] 소제목 디자인 변경: 가운데 정렬(center)로 롤백, 들여쓰기 0
                style = '''
                @page { margin: 5%; }
                body { font-family: sans-serif; line-height: 1.6; }
                h2 { text-align: center; font-size: 1.4em; margin-top: 1.5em; margin-bottom: 0.2em; }
                .sub-title { text-align: center; font-size: 1.2em; text-indent: 0; margin-top: 0; margin-bottom: 1.0em; }
                p { text-indent: 1em; margin: 0 0 0.6em 0; text-align: justify; }
                .scene-divider { text-align: center; text-indent: 0; margin: 0.5em 0; }
                '''
                nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style)
                book.add_item(nav_css)

                epub_chapters = []
                for i, (ch_title, ch_sub_title, ch_lines) in enumerate(chapters):
                    
                    # [개선] '목차에 이어서 표시하기' 옵션이 켜져 있고 소제목이 있다면 제목 텍스트를 결합
                    display_title = ch_title
                    if sub_title_option and join_title_option and ch_sub_title:
                        display_title = f"{ch_title} - {ch_sub_title}" if "화" in ch_title else f"{ch_title} {ch_sub_title}"

                    html_content = f'<html><head><link rel="stylesheet" href="style/nav.css" type="text/css"/></head><body>'
                    
                    # 화 제목 상단 공백
                    html_content += '<p style="text-indent:0;">&nbsp;</p>'
                    html_content += f'<h2>{display_title}</h2>'
                    
                    if ch_sub_title and not join_title_option:
                        # [개선] 목차에 이어붙이지 않는 경우: 화 제목 바로 아랫줄에 가운데 정렬로 배치
                        html_content += f'<p class="sub-title">{ch_sub_title}</p>'
                        
                        # 소제목 끝나고 본문 시작 전 물리적인 빈 줄 1개 분량 여백
                        html_content += '<p style="text-indent:0;">&nbsp;</p>'
                    else:
                        # 소제목이 없거나 목차에 이어붙인 경우 제목 밑에 빈 줄 3개
                        html_content += '<p style="text-indent:0;">&nbsp;</p>'
                        html_content += '<p style="text-indent:0;">&nbsp;</p>'
                        html_content += '<p style="text-indent:0;">&nbsp;</p>'
                    
                    for line in ch_lines:
                        if line == '* * *' or line.replace(' ', '') == '***':
                            html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            html_content += f'<p class="scene-divider">{line}</p>'
                            html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            html_content += '<p style="text-indent:0;">&nbsp;</p>'
                        else:
                            html_content += f'<p>{line}</p>'
                    html_content += '</body></html>'

                    # 실제 앱 목차 트리 구조에도 display_title을 반영
                    chapter = epub.EpubHtml(title=display_title, file_name=f'chap_{i+1}.xhtml', lang='ko')
                    chapter.content = html_content
                    chapter.add_item(nav_css)
                    book.add_item(chapter)
                    epub_chapters.append(chapter)

                book.toc = tuple(epub_chapters)
                book.add_item(epub.EpubNcx())
                book.add_item(epub.EpubNav())
                book.spine = epub_chapters 

                epub_fp = io.BytesIO()
                epub.write_epub(epub_fp, book, {})
                epub_data = epub_fp.getvalue()

                st.success("🎉 변환 및 리스타일링 성공! 아래 버튼을 눌러 저장하세요.")
                st.download_button(
                    label="📥 가공된 EPUB 파일 다운로드",
                    data=epub_data,
                    file_name=f"{title}.epub",
                    mime="application/epub+zip",
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")
else:
    st.info("파일 업로드 및 도서 정보를 모두 입력하시면 변환 버튼이 나타납니다.")
