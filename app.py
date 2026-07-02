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

# [개선] 요청에 따라 특정 소설 예시를 빼고 깔끔한 안내 문구로 교체했습니다.
st.info("💡 팁: 제목 뒤에 숫자가 붙는 웹소설 형태의 파일은 [내가 직접 기준 단어 지정]을 누르고 해당 단어(예: 화 또는 장)를 입력하시면 정확하게 분리됩니다!")
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
                        txt_content = raw_bytes.decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue
                
                if txt_content is None:
                    txt_content = raw_bytes.decode("utf-8", errors="ignore")
                
                book = epub.EpubBook()
                book.set_identifier('web_generated_id_12345')
                book.set_title(title)
                book.set_language('ko')
                book.add_author(author)

                if cover_file:
                    book.set_cover("cover.jpg", cover_file.read())

                # [개선] h2(화 제목)의 글자 크기를 기존 기본값(2em)에서 1.6em으로 줄이고, 여백을 조절했습니다.
                style = '''
                @page { margin: 5%; }
                body { font-family: sans-serif; line-height: 1.6; }
                h2 { text-align: center; font-size: 1.6em; margin-top: 1.5em; margin-bottom: 0.8em; }
                p { text-indent: 1em; margin: 0 0 0.6em 0; text-align: justify; }
                .scene-divider { text-align: center; text-indent: 0; margin: 0.5em 0; }
                '''
                nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style)
                book.add_item(nav_css)

                lines = txt_content.splitlines()
                chapters = []
                current_chapter_title = "프롤로그"
                current_chapter_lines = []
                compiled_pattern = re.compile(toc_pattern)

                for line in lines:
                    line = line.strip()
                    if not line: 
                        continue
                    
                    if compiled_pattern.match(line):
                        if current_chapter_lines:
                            chapters.append((current_chapter_title, current_chapter_lines))
                            current_chapter_lines = []
                        current_chapter_title = line
                    else:
                        current_chapter_lines.append(line)
                        
                if current_chapter_lines:
                    chapters.append((current_chapter_title, current_chapter_lines))

                epub_chapters = []
                for i, (ch_title, ch_lines) in enumerate(chapters):
                    html_content = f'<html><head><link rel="stylesheet" href="style/nav.css" type="text/css"/></head><body>'
                    
                    # [개선] 화 제목 상단에도 무조건 한 줄 공백을 삽입합니다.
                    html_content += '<p style="text-indent:0;">&nbsp;</p>'
                    
                    html_content += f'<h2>{ch_title}</h2>'
                    
                    # 화 제목 하단에 빈 줄 3개 유지
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

                    chapter = epub.EpubHtml(title=ch_title, file_name=f'chap_{i+1}.xhtml', lang='ko')
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

                st.success("🎉 변환 성공! 아래 버튼을 눌러 저장하세요.")
                st.download_button(
                    label="📥 EPUB 파일 다운로드",
                    data=epub_data,
                    file_name=f"{title}.epub",
                    mime="application/epub+zip",
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")
else:
    st.info("파일 업로드 및 도서 정보를 모두 입력하시면 변환 버튼이 나타납니다.")
