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
cover_file = st.file_uploader("표지 이미지 (*.jpg, *.png, *.webp) 선택 (선택사항)", type=["jpg", "jpeg", "png", "webp"])

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
join_title_option = st.checkbox("➔ 선택사항: 목차(화수) 뒤에 소제목을 이어서 표시하기", value=False, disabled=not sub_title_option)

# [신규 기능] 대사 앞뒤 자동 줄바꿈 옵션 추가
st.markdown("**본문 대사 레이아웃 설정**")
dialogue_spacing_option = st.checkbox("대사(따옴표)와 일반 본문 사이에 자동으로 빈 줄 넣기", value=True)

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

                # --- 공통: 새 EPUB 빌드 구역 ---
                book = epub.EpubBook()
                book.set_identifier('web_generated_id_12345')
                book.set_title(title)
                book.set_language('ko')
                book.add_author(author)

                if cover_file:
                    cover_ext = os.path.splitext(cover_file.name)[1].lower()
                    if cover_ext == ".webp":
                        book.set_cover("cover.webp", cover_file.read())
                    else:
                        book.set_cover("cover.jpg", cover_file.read())
                elif is_epub:
                    for item in input_book.get_items():
                        if item.get_type() == 4: 
                            if "cover" in item.get_name().lower():
                                book.set_cover("cover.jpg", item.get_content())
                                break

                # 스타일 시트
                style = '''
                @page { margin: 5%; }
                body { font-family: sans-serif; line-height: 1.6; }
                h2 { text-align: center; font-size: 1.4em; margin-top: 1.5em; margin-bottom: 0.2em; }
                .sub-title { text-align: center; font-size: 1.1em; text-indent: 0; margin-top: 0; margin-bottom: 1.0em; }
                p { text-indent: 1em; margin: 0 0 0.6em 0; text-align: justify; }
                .scene-divider { text-align: center; text-indent: 0; margin: 0.5em 0; }
                '''
                nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style)
                book.add_item(nav_css)

                # 대화/독백 따옴표 패턴 정의
                dialogue_quotes = ("“", "”", '"', "‘", "’", "'")

                epub_chapters = []
                for i, (ch_title, ch_sub_title, ch_lines) in enumerate(chapters):
                    
                    display_title = ch_title
                    if sub_title_option and join_title_option and ch_sub_title:
                        display_title = f"{ch_title} {ch_sub_title}"

                    html_content = f'<html><head><link rel="stylesheet" href="style/nav.css" type="text/css"/></head><body>'
                    
                    # 화 제목 상단 공백
                    html_content += '<p style="text-indent:0;">&nbsp;</p>'
                    html_content += f'<h2>{display_title}</h2>'
                    
                    if ch_sub_title and not join_title_option:
                        html_content += f'<p class="sub-title">{ch_sub_title}</p>'
                        html_content += '<p style="text-indent:0;">&nbsp;</p>'
                        html_content += '<p style="text-indent:0;">&nbsp;</p>'
                        html_content += '<p style="text-indent:0;">&nbsp;</p>'
                    else:
                        html_content += '<p style="text-indent:0;">&nbsp;</p>'
                        html_content += '<p style="text-indent:0;">&nbsp;</p>'
                        html_content += '<p style="text-indent:0;">&nbsp;</p>'
                    
                    # [핵심 개선] 대사/본문 전환 자동 줄바꿈 렌더링 로직
                    prev_is_dialogue = None # 이전 문단이 대사였는지 기록하는 상태 플래그
                    
                    for line in ch_lines:
                        # 1. 장면 전환 기호 우선 처리
                        if line == '* * *' or line.replace(' ', '') == '***':
                            html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            html_content += f'<p class="scene-divider">{line}</p>'
                            html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            prev_is_dialogue = None # 장면이 전환되었으므로 대사 상태 초기화
                            continue
                        
                        # 2. 이번 문단이 대사인지 여부 판단 (따옴표로 시작하거나 대화 마크(-) 등으로 시작할 때)
                        is_dialogue = line.startswith(dialogue_quotes) or line.startswith("-")
                        
                        # 3. 대사 Spacing 옵션이 켜져 있을 때 조건별 줄바꿈 삽입
                        if dialogue_spacing_option and prev_is_dialogue is not None:
                            # [조건 A] 일반 본문 ➔ 대사로 바뀔 때
                            if not prev_is_dialogue and is_dialogue:
                                html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            # [조건 B] 대사 ➔ 일반 본문으로 돌아올 때
                            elif prev_is_dialogue and not is_dialogue:
                                html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            # (대사 ➔ 대사 연속 상황이나 본문 ➔ 본문 연속 상황에서는 추가하지 않음!)

                        # 4. 본문 문단 추가 및 상태 업데이트
                        html_content += f'<p>{line}</p>'
                        prev_is_dialogue = is_dialogue

                    html_content += '</body></html>'

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
