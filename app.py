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

# 도서명과 일치하는 본문 줄 삭제 옵션
remove_title_lines_option = st.checkbox("➔ 선택사항: 본문에서 도서명(제목)과 똑같은 줄은 자동으로 삭제하기", value=True)

# 다음 줄 소제목 설정 구역
sub_title_option = st.checkbox("화수 제목 다음 줄을 소제목으로 인식하여 효과 적용하기", value=False)
join_title_option = st.checkbox("➔ 선택사항: 목차(화수) 뒤에 소제목을 이어서 표시하기", value=False, disabled=not sub_title_option)

# 시스템창 디자인 설정 구역
st.markdown("**본문 시스템창(상태창) 레이아웃 설정**")
use_system_window = st.checkbox("특정 문자로 둘러싸인 줄을 '시스템창' 스타일 상자로 만들기", value=False)
col1, col2 = st.columns(2)
with col1:
    sys_start = st.text_input("시스템창 시작 문자", value="[", disabled=not use_system_window)
with col2:
    sys_end = st.text_input("시스템창 끝 문자", value="]", disabled=not use_system_window)

# 게임 채팅 설정 구역
st.markdown("**본문 게임 채팅창 레이아웃 설정**")
use_game_chat = st.checkbox("특정 문자로 둘러싸인 줄을 '인게임 채팅방' 스타일로 만들기", value=False)
col_g1, col_g2 = st.columns(2)
with col_g1:
    game_start = st.text_input("게임채팅 시작 문자", value="{", disabled=not use_game_chat)
with col_g2:
    game_end = st.text_input("게임채팅 끝 문자", value="}", disabled=not use_game_chat)

# 본문 메신저(채팅창) 레이아웃 설정 구역
st.markdown("**본문 메신저(채팅창) 레이아웃 설정**")
use_chat_window = st.checkbox("특정 문자로 둘러싸인 줄을 '메신저 채팅방(iMessage)' 스타일로 만들기", value=False)
col_chat1, col_chat2 = st.columns(2)
with col_chat1:
    chat_start = st.text_input("메시지 시작 문자", value="<", disabled=not use_chat_window)
with col_chat2:
    chat_end = st.text_input("메시지 끝 문자", value=">", disabled=not use_chat_window)

# [신규 기능] 인터넷 게시글 및 댓글 레이아웃 설정 구역
st.markdown("**본문 인터넷 게시글 및 댓글 설정**")
use_board_post = st.checkbox("특정 문자로 게시글(커뮤니티) 및 댓글 구현하기", value=False)
col_b1, col_b2, col_b3, col_b4 = st.columns(4)
with col_b1:
    post_start = st.text_input("게시글 시작 문자", value="~", disabled=not use_board_post)
with col_b2:
    post_end = st.text_input("게시글 끝 문자", value="~", disabled=not use_board_post)
with col_b3:
    reply_start = st.text_input("댓글 시작 문자", value="|", disabled=not use_board_post)
with col_b4:
    reply_end = st.text_input("댓글 끝 문자", value="|", disabled=not use_board_post)

# 본문 대사 레이아웃 설정
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
                        
                        # 도서명과 완전히 동일한 줄 삭제
                        if remove_title_lines_option and title:
                            normalized_line = line.replace(" ", "").lower()
                            normalized_title = title.replace(" ", "").lower()
                            if normalized_line == normalized_title:
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

                # [개선] 인터넷 게시글 및 댓글 스타일 추가 탑재
                style = '''
                @page { margin: 5%; }
                body { font-family: sans-serif; line-height: 1.6; }
                h2 { text-align: center; font-size: 1.4em; margin-top: 1.5em; margin-bottom: 0.2em; }
                .sub-title { text-align: center; font-size: 1.1em; text-indent: 0; margin-top: 0; margin-bottom: 1.0em; }
                p { text-indent: 1em; margin: 0 0 0.6em 0; text-align: justify; }
                .scene-divider { text-align: center; text-indent: 0; margin: 0.5em 0; }
                .system-box { 
                    border: 1px solid #4a90e2; 
                    background-color: #f0f6fc; 
                    padding: 10px 14px; 
                    margin: 0.5em 1em; 
                    text-indent: 0; 
                    border-radius: 6px; 
                    text-align: center;
                    font-size: 0.95em;
                    color: #1a4f8a;
                    font-weight: bold;
                }
                /* 아이메시지용 커스텀 스타일 */
                .chat-my-block { text-align: right; text-indent: 0; margin: 0.4em 0; }
                .chat-bubble-my { 
                    display: inline-block; 
                    background-color: #007aff; 
                    color: #ffffff; 
                    padding: 8px 14px; 
                    border-radius: 16px 16px 4px 16px; 
                    max-width: 75%; 
                    text-align: left; 
                    font-size: 0.95em;
                }
                .chat-other-block { text-align: left; text-indent: 0; margin: 0.4em 0; }
                .chat-sender-name { 
                    font-size: 0.8em; 
                    color: #8e8e93; 
                    font-weight: bold; 
                    display: block; 
                    margin-bottom: 2px; 
                    margin-left: 4px;
                }
                .chat-bubble-other { 
                    display: inline-block; 
                    background-color: #e9e9eb; 
                    color: #000000; 
                    padding: 8px 14px; 
                    border-radius: 16px 16px 16px 4px; 
                    max-width: 75%; 
                    text-align: left; 
                    font-size: 0.95em;
                }
                /* 게임 채팅 전용 블랙박스 */
                .game-chat-box {
                    background-color: #1c1c1e;
                    border-left: 4px solid #8e8e93;
                    padding: 8px 12px;
                    margin: 0.4em 0.8em;
                    text-indent: 0;
                    border-radius: 4px;
                    font-family: monospace, sans-serif;
                    font-size: 0.9em;
                    line-height: 1.4;
                    text-align: left;
                }
                .g-normal { color: #ffffff; }
                .g-party { color: #82ccdd; }
                .g-guild { color: #78e08f; }
                .g-whisper { color: #f8a5c2; }
                .g-sys { color: #fad390; }
                .g-team { color: #ff9f43; }
                .g-friend { color: #feed6d; }

                /* 인터넷 게시판 게시글 박스 */
                .board-post-box {
                    background-color: #fbfbfb;
                    border: 1px solid #e1e4e6;
                    border-radius: 6px;
                    padding: 16px;
                    margin: 0.8em 0.4em;
                    text-indent: 0;
                }
                .board-post-title {
                    font-size: 1.15em;
                    font-weight: bold;
                    color: #1e1e24;
                    border-bottom: 2px solid #e1e4e6;
                    padding-bottom: 10px;
                    margin-bottom: 12px;
                    text-indent: 0;
                }
                .board-post-content {
                    font-size: 0.95em;
                    color: #333333;
                    line-height: 1.5;
                    text-indent: 0;
                }

                /* 인터넷 게시판 댓글 세트 */
                .board-reply-container {
                    background-color: #f6f8fa;
                    border: 1px solid #e1e4e6;
                    border-radius: 6px;
                    padding: 10px 14px;
                    margin: 0.5em 0.4em;
                    text-indent: 0;
                }
                .board-reply-item {
                    font-size: 0.9em;
                    border-bottom: 1px solid #eef1f2;
                    padding: 6px 0;
                    color: #444444;
                    text-indent: 0;
                }
                .board-reply-item:last-child {
                    border-bottom: none;
                }
                .board-reply-author {
                    font-weight: bold;
                    color: #1e272e;
                    margin-right: 6px;
                }
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
                    
                    # 대사/본문 전환 자동 줄바꿈 렌더링 로직용 플래그
                    prev_is_dialogue = None
                    prev_is_system = False
                    prev_is_chat = False
                    prev_is_game_chat = False
                    
                    # 게시글/댓글을 누적 수집하기 위한 임시 보관 리스트 및 상태
                    post_buffer = []
                    reply_buffer = []
                    is_collecting_post = False
                    is_collecting_reply = False
                    
                    for line in ch_lines:
                        # 1. 장면 전환 기호 우선 처리
                        if line == '* * *' or line.replace(' ', '') == '***':
                            # 수집 중이던 게시글이나 댓글 블록 털어내기
                            if is_collecting_post and post_buffer:
                                p_title = post_buffer[0]
                                p_body = "<br/>".join(post_buffer[1:]) if len(post_buffer) > 1 else ""
                                html_content += f'<div class="board-post-box"><div class="board-post-title">{p_title}</div><div class="board-post-content">{p_body}</div></div>'
                                post_buffer = []
                                is_collecting_post = False
                            
                            if is_collecting_reply and reply_buffer:
                                html_content += '<div class="board-reply-container">'
                                for r_item in reply_buffer:
                                    if ":" in r_item:
                                        r_author, r_text = r_item.split(":", 1)
                                        html_content += f'<div class="board-reply-item"><span class="board-reply-author">{r_author.strip()}</span>: {r_text.strip()}</div>'
                                    else:
                                        html_content += f'<div class="board-reply-item">{r_item}</div>'
                                html_content += '</div>'
                                reply_buffer = []
                                is_collecting_reply = False

                            html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            html_content += f'<p class="scene-divider">{line}</p>'
                            html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            prev_is_dialogue = None
                            prev_is_system = False
                            prev_is_chat = False
                            prev_is_game_chat = False
                            continue
                        
                        # [인터넷 게시글/댓글 수집 전처리 영역]
                        # 가. 게시글 감지
                        if use_board_post and post_start and post_end and line.startswith(post_start) and line.endswith(post_end):
                            inner_post = line[len(post_start):-len(post_end)].strip()
                            if not is_collecting_post:
                                # 이전 요소 마무리
                                if is_collecting_reply and reply_buffer:
                                    html_content += '<div class="board-reply-container">'
                                    for r_item in reply_buffer:
                                        if ":" in r_item:
                                            r_author, r_text = r_item.split(":", 1)
                                            html_content += f'<div class="board-reply-item"><span class="board-reply-author">{r_author.strip()}</span>: {r_text.strip()}</div>'
                                        else:
                                            html_content += f'<div class="board-reply-item">{r_item}</div>'
                                    html_content += '</div>'
                                    reply_buffer = []
                                    is_collecting_reply = False
                                
                                is_collecting_post = True
                                html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            
                            post_buffer.append(inner_post)
                            prev_is_dialogue = None
                            prev_is_system = False
                            prev_is_chat = False
                            prev_is_game_chat = False
                            continue
                        
                        # 나. 댓글 감지
                        elif use_board_post and reply_start and reply_end and line.startswith(reply_start) and line.endswith(reply_end):
                            inner_reply = line[len(reply_start):-len(reply_end)].strip()
                            if not is_collecting_reply:
                                # 이전 요소 마무리
                                if is_collecting_post and post_buffer:
                                    p_title = post_buffer[0]
                                    p_body = "<br/>".join(post_buffer[1:]) if len(post_buffer) > 1 else ""
                                    html_content += f'<div class="board-post-box"><div class="board-post-title">{p_title}</div><div class="board-post-content">{p_body}</div></div>'
                                    post_buffer = []
                                    is_collecting_post = False
                                
                                is_collecting_reply = True
                                html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            
                            reply_buffer.append(inner_reply)
                            prev_is_dialogue = None
                            prev_is_system = False
                            prev_is_chat = False
                            prev_is_game_chat = False
                            continue
                        
                        # 다. 수집 상태였는데 일반 텍스트가 나왔다면? 수집 완료 털어내기
                        else:
                            if is_collecting_post and post_buffer:
                                p_title = post_buffer[0]
                                p_body = "<br/>".join(post_buffer[1:]) if len(post_buffer) > 1 else ""
                                html_content += f'<div class="board-post-box"><div class="board-post-title">{p_title}</div><div class="board-post-content">{p_body}</div></div>'
                                post_buffer = []
                                is_collecting_post = False
                                html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            
                            if is_collecting_reply and reply_buffer:
                                html_content += '<div class="board-reply-container">'
                                for r_item in reply_buffer:
                                    if ":" in r_item:
                                        r_author, r_text = r_item.split(":", 1)
                                        html_content += f'<div class="board-reply-item"><span class="board-reply-author">{r_author.strip()}</span>: {r_text.strip()}</div>'
                                    else:
                                        html_content += f'<div class="board-reply-item">{r_item}</div>'
                                html_content += '</div>'
                                reply_buffer = []
                                is_collecting_reply = False
                                html_content += '<p style="text-indent:0;">&nbsp;</p>'

                        # 2. 게임채팅 조건 판단 및 렌더링
                        is_game_chat = False
                        if use_game_chat and game_start and game_end:
                            if line.startswith(game_start) and line.endswith(game_end):
                                is_game_chat = True
                        
                        if is_game_chat:
                            if not prev_is_game_chat:
                                html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            elif prev_is_game_chat:
                                html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            
                            inner_text = line[len(game_start):-len(game_end)].strip()
                            
                            chat_class = "g-normal"
                            if inner_text.startswith("[길드]"):
                                chat_class = "g-guild"
                            elif inner_text.startswith("[파티]"):
                                chat_class = "g-party"
                            elif inner_text.startswith("[귓속말]") or inner_text.startswith("[귓]"):
                                chat_class = "g-whisper"
                            elif inner_text.startswith("[시스템]") or inner_text.startswith("[공지]"):
                                chat_class = "g-sys"
                            elif inner_text.startswith("[팀]"):
                                chat_class = "g-team"
                            elif inner_text.startswith("[친구]") or inner_text.startswith("[친]"):
                                chat_class = "g-friend"
                            
                            html_content += f'<div class="game-chat-box {chat_class}">{inner_text}</div>'
                            
                            prev_is_dialogue = None
                            prev_is_system = False
                            prev_is_chat = False
                            prev_is_game_chat = True
                            continue
                            
                        # 3. 메신저(채팅창) 렌더링 로직
                        is_chat = False
                        if use_chat_window and chat_start and chat_end:
                            if line.startswith(chat_start) and line.endswith(chat_end):
                                is_chat = True
                        
                        if is_chat:
                            if prev_is_game_chat:
                                html_content += '<p style="text-indent:0;">&nbsp;</p>'
                                
                            if not prev_is_chat:
                                html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            
                            inner_text = line[len(chat_start):-len(chat_end)].strip()
                            
                            if ":" in inner_text:
                                msg_sender, msg_content = inner_text.split(":", 1)
                                msg_sender = msg_sender.strip()
                                msg_content = msg_content.strip()
                                html_content += f'<div class="chat-other-block"><span class="chat-sender-name">{msg_sender}</span><span class="chat-bubble-other">{msg_content}</span></div>'
                            else:
                                html_content += f'<div class="chat-my-block"><span class="chat-bubble-my">{inner_text}</span></div>'
                            
                            prev_is_dialogue = None
                            prev_is_system = False
                            prev_is_chat = True
                            prev_is_game_chat = False
                            
                        # 4. 시스템창 조건 판단
                        elif use_system_window and sys_start and sys_end and line.startswith(sys_start) and line.endswith(sys_end):
                            if prev_is_chat or prev_is_game_chat:
                                html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            
                            if prev_is_system:
                                html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            else:
                                html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            
                            html_content += f'<p class="system-box">{line}</p>'
                            prev_is_dialogue = None
                            prev_is_system = True
                            prev_is_chat = False
                            prev_is_game_chat = False
                        
                        # 5. 일반 본문 / 대사 렌더링
                        else:
                            if prev_is_chat or prev_is_system or prev_is_game_chat:
                                html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            
                            is_dialogue = line.startswith(dialogue_quotes) or line.startswith("-")
                            
                            if dialogue_spacing_option and prev_is_dialogue is not None:
                                if not prev_is_dialogue and is_dialogue:
                                    html_content += '<p style="text-indent:0;">&nbsp;</p>'
                                elif prev_is_dialogue and not is_dialogue:
                                    html_content += '<p style="text-indent:0;">&nbsp;</p>'

                            html_content += f'<p>{line}</p>'
                            prev_is_dialogue = is_dialogue
                            prev_is_system = False
                            prev_is_chat = False
                            prev_is_game_chat = False

                    # 루프 종료 후 혹시 남아있던 버퍼 털어내기
                    if is_collecting_post and post_buffer:
                        p_title = post_buffer[0]
                        p_body = "<br/>".join(post_buffer[1:]) if len(post_buffer) > 1 else ""
                        html_content += f'<div class="board-post-box"><div class="board-post-title">{p_title}</div><div class="board-post-content">{p_body}</div></div>'
                    if is_collecting_reply and reply_buffer:
                        html_content += '<div class="board-reply-container">'
                        for r_item in reply_buffer:
                            if ":" in r_item:
                                r_author, r_text = r_item.split(":", 1)
                                html_content += f'<div class="board-reply-item"><span class="board-reply-author">{r_author.strip()}</span>: {r_text.strip()}</div>'
                            else:
                                html_content += f'<div class="board-reply-item">{r_item}</div>'
                        html_content += '</div>'

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
