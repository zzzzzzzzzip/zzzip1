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

# --- 세션 상태(Session State) 초기화 ---
# 사용자가 버튼을 누를 때마다 입력 칸이 동적으로 늘어나도록 리스트로 관리합니다.
if "sys_pairs" not in st.session_state:
    st.session_state.sys_pairs = [("[", "]")]
if "game_pairs" not in st.session_state:
    st.session_state.game_pairs = [("{", "}")]
if "chat_pairs" not in st.session_state:
    st.session_state.chat_pairs = [("<", ">")]
if "post_pairs" not in st.session_state:
    st.session_state.post_pairs = [("~", "~")]
if "reply_pairs" not in st.session_state:
    st.session_state.reply_pairs = [("|", "|")]

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
remove_title_lines_option = st.checkbox("➔ 선택사항: 본문에서 도서명(제목)과 똑같은 줄은 자동으로 삭제하기", value=True)

sub_title_option = st.checkbox("화수 제목 다음 줄을 소제목으로 인식하여 효과 적용하기", value=False)
join_title_option = st.checkbox("➔ 선택사항: 목차(화수) 뒤에 소제목을 이어서 표시하기", value=False, disabled=not sub_title_option)


# --- 💡 [핵심 개선] 동적 기호 레이아웃 생성 도우미 함수 ---
def render_dynamic_inputs(section_title, state_key, checkbox_label):
    st.markdown(f"**{section_title}**")
    is_enabled = st.checkbox(checkbox_label, value=False, key=f"enable_{state_key}")
    
    pairs = st.session_state[state_key]
    final_pairs = []
    
    if is_enabled:
        for idx, (start_val, end_val) in enumerate(pairs):
            c1, c2, c3 = st.columns([4, 4, 2])
            with c1:
                s_input = st.text_input(f"시작 기호 {idx+1}", value=start_val, key=f"{state_key}_s_{idx}")
            with c2:
                e_input = st.text_input(f"끝 기호 {idx+1}", value=end_val, key=f"{state_key}_e_{idx}")
            with c3:
                st.write("") # 패딩용
                st.write("") 
                # 기호 쌍이 2개 이상일 때만 삭제 버튼 활성화
                if st.button("❌ 삭제", key=f"del_{state_key}_{idx}", disabled=len(pairs) <= 1):
                    st.session_state[state_key].pop(idx)
                    st.rerun()
            final_pairs.append((s_input, e_input))
            
        if st.button("➕ 기호 조건 추가하기", key=f"add_{state_key}"):
            st.session_state[state_key].append(("", ""))
            st.rerun()
            
        # 화면 입력값을 세션 상태에 실시간 동기화
        st.session_state[state_key] = final_pairs
        return is_enabled, final_pairs
    return is_enabled, []

# 각 레이아웃 구역 동적 입력창 구현
use_system_window, final_sys_pairs = render_dynamic_inputs("본문 시스템창(상태창) 레이아웃 설정", "sys_pairs", "특정 문자로 둘러싸인 줄을 '시스템창' 스타일 상자로 만들기")
use_game_chat, final_game_pairs = render_dynamic_inputs("본문 게임 채팅창 레이아웃 설정", "game_pairs", "특정 문자로 둘러싸인 줄을 '인게임 채팅방' 스타일로 만들기")
use_chat_window, final_chat_pairs = render_dynamic_inputs("본문 메신저(채팅창) 레이아웃 설정", "chat_pairs", "특정 문자로 둘러싸인 줄을 '메신저 채팅방(iMessage)' 스타일로 만들기")

st.markdown("**본문 인터넷 게시글 및 댓글 설정**")
use_board_post = st.checkbox("특정 문자로 게시글(커뮤니티) 및 댓글 구현하기", value=False)
final_post_pairs = []
final_reply_pairs = []
if use_board_post:
    # 게시글 기호 동적 관리
    for idx, (s_v, e_v) in enumerate(st.session_state.post_pairs):
        c1, c2, c3 = st.columns([4, 4, 2])
        with c1: s_in = st.text_input(f"게시글 시작 {idx+1}", value=s_v, key=f"post_s_{idx}")
        with c2: e_in = st.text_input(f"게시글 끝 {idx+1}", value=e_v, key=f"post_e_{idx}")
        with c3:
            st.write(""); st.write("")
            if st.button("❌ 삭제", key=f"del_post_{idx}", disabled=len(st.session_state.post_pairs) <= 1):
                st.session_state.post_pairs.pop(idx); st.rerun()
        final_post_pairs.append((s_in, e_in))
    if st.button("➕ 게시글 기호 추가"):
        st.session_state.post_pairs.append(("", "")); st.rerun()
    st.session_state.post_pairs = final_post_pairs

    # 댓글 기호 동적 관리
    for idx, (s_v, e_v) in enumerate(st.session_state.reply_pairs):
        c1, c2, c3 = st.columns([4, 4, 2])
        with c1: s_in = st.text_input(f"댓글 시작 {idx+1}", value=s_v, key=f"reply_s_{idx}")
        with c2: e_in = st.text_input(f"댓글 끝 {idx+1}", value=e_v, key=f"reply_e_{idx}")
        with c3:
            st.write(""); st.write("")
            if st.button("❌ 삭제", key=f"del_reply_{idx}", disabled=len(st.session_state.reply_pairs) <= 1):
                st.session_state.reply_pairs.pop(idx); st.rerun()
        final_reply_pairs.append((s_in, e_in))
    if st.button("➕ 댓글 기호 추가"):
        st.session_state.reply_pairs.append(("", "")); st.rerun()
    st.session_state.reply_pairs = final_reply_pairs

st.markdown("**본문 대사 레이아웃 설정**")
dialogue_spacing_option = st.checkbox("대사(따옴표)와 일반 본문 사이에 자동으로 빈 줄 넣기", value=True)

st.info("💡 팁: 기존에 갖고 있던 EPUB 파일을 업로드하면 목차 구분 설정을 건드릴 필요 없이, 내 커스텀 스타일만 똑같이 입혀서 새로 내려받아 줍니다!")
st.caption("※ 들여쓰기는 문단 맨 앞에 1글자 크기(1em)로 자동 적용됩니다.")


# --- 기호 일치 여부를 다중 쌍으로 체크하는 함수 ---
def check_match(line, is_enabled, pairs):
    if not is_enabled:
        return False, "", ""
    for start_sym, end_sym in pairs:
        if start_sym and end_sym and line.startswith(start_sym) and line.endswith(end_sym):
            return True, start_sym, end_sym
    return False, "", ""


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
                            ch_lines = [p.get_text().strip() for p in soup.find_all("p") if p.get_text().strip()]
                            if ch_lines:
                                if ch_lines[0] == ch_title: ch_lines.pop(0)
                                if ch_lines: chapters.append((ch_title, None, ch_lines))
                else:
                    # --- 기존 TXT 파일 파싱 구역 ---
                    raw_bytes = uploaded_file.read()
                    txt_content = None
                    encodings = ["utf-8-sig", "utf-8", "cp949", "utf-16", "euc-kr"]
                    for enc in encodings:
                        try:
                            txt_content = raw_bytes.decode(enc)
                            break
                        except UnicodeDecodeError: continue
                    if txt_content is None: txt_content = raw_bytes.decode("utf-8", errors="ignore")

                    lines = txt_content.splitlines()
                    current_chapter_title = "프롤로그"
                    current_sub_title = None
                    current_chapter_lines = []
                    compiled_pattern = re.compile(toc_pattern)

                    for line in lines:
                        line = line.strip()
                        if not line: continue
                        if remove_title_lines_option and title:
                            if line.replace(" ", "").lower() == title.replace(" ", "").lower(): continue
                        
                        match = compiled_pattern.search(line)
                        if match:
                            if current_chapter_lines or current_sub_title:
                                chapters.append((current_chapter_title, current_sub_title, current_chapter_lines))
                                current_chapter_lines, current_sub_title = [], None
                            current_chapter_title = match.group().strip() if clean_title_option else line
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
                    book.set_cover("cover.webp" if cover_ext == ".webp" else "cover.jpg", cover_file.read())
                elif is_epub:
                    for item in input_book.get_items():
                        if item.get_type() == 4 and "cover" in item.get_name().lower():
                            book.set_cover("cover.jpg", item.get_content())
                            break

                style = '''
                @page { margin: 5%; }
                body { font-family: sans-serif; line-height: 1.6; }
                h2 { text-align: center; font-size: 1.4em; margin-top: 1.5em; margin-bottom: 0.2em; }
                .sub-title { text-align: center; font-size: 1.1em; text-indent: 0; margin-top: 0; margin-bottom: 1.0em; }
                p { text-indent: 1em; margin: 0 0 0.6em 0; text-align: justify; }
                .scene-divider { text-align: center; text-indent: 0; margin: 0.5em 0; }
                .system-box { border: 1px solid #4a90e2; background-color: #f0f6fc; padding: 10px 14px; margin: 0.5em 1em; text-indent: 0; border-radius: 6px; text-align: center; font-size: 0.95em; color: #1a4f8a; font-weight: bold; }
                .chat-my-block { text-align: right; text-indent: 0; margin: 0.4em 0; }
                .chat-bubble-my { display: inline-block; background-color: #007aff; color: #ffffff; padding: 8px 14px; border-radius: 16px 16px 4px 16px; max-width: 75%; text-align: left; font-size: 0.95em; }
                .chat-other-block { text-align: left; text-indent: 0; margin: 0.4em 0; }
                .chat-sender-name { font-size: 0.8em; color: #8e8e93; font-weight: bold; display: block; margin-bottom: 2px; margin-left: 4px; }
                .chat-bubble-other { display: inline-block; background-color: #e9e9eb; color: #000000; padding: 8px 14px; border-radius: 16px 16px 16px 4px; max-width: 75%; text-align: left; font-size: 0.95em; }
                .game-chat-box { background-color: #1c1c1e; border-left: 4px solid #8e8e93; padding: 8px 12px; margin: 0.4em 0.8em; text-indent: 0; border-radius: 4px; font-family: monospace, sans-serif; font-size: 0.9em; line-height: 1.4; text-align: left; }
                .g-normal { color: #ffffff; } .g-party { color: #82ccdd; } .g-guild { color: #78e08f; } .g-whisper { color: #f8a5c2; } .g-sys { color: #fad390; } .g-team { color: #ff9f43; } .g-friend { color: #feed6d; }
                .board-post-box { background-color: #fbfbfb; border: 1px solid #e1e4e6; border-radius: 6px; padding: 16px; margin: 0.8em 0.4em; text-indent: 0; }
                .board-post-title { font-size: 1.15em; font-weight: bold; color: #1e1e24; border-bottom: 2px solid #e1e4e6; padding-bottom: 10px; margin-bottom: 12px; text-indent: 0; }
                .board-post-content { font-size: 0.95em; color: #333333; line-height: 1.5; text-indent: 0; }
                .board-reply-container { background-color: #f6f8fa; border: 1px solid #e1e4e6; border-radius: 6px; padding: 10px 14px; margin: 0.5em 0.4em; text-indent: 0; }
                .board-reply-item { font-size: 0.9em; border-bottom: 1px solid #eef1f2; padding: 6px 0; color: #444444; text-indent: 0; }
                .board-reply-item:last-child { border-bottom: none; }
                .board-reply-author { font-weight: bold; color: #1e272e; margin-right: 6px; }
                '''
                nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style)
                book.add_item(nav_css)

                dialogue_quotes = ("“", "”", '"', "‘", "’", "'")

                epub_chapters = []
                for i, (ch_title, ch_sub_title, ch_lines) in enumerate(chapters):
                    display_title = f"{ch_title} {ch_sub_title}" if sub_title_option and join_title_option and ch_sub_title else ch_title
                    html_content = f'<html><head><link rel="stylesheet" href="style/nav.css" type="text/css"/></head><body>'
                    html_content += '<p style="text-indent:0;">&nbsp;</p>'
                    html_content += f'<h2>{display_title}</h2>'
                    
                    if ch_sub_title and not join_title_option:
                        html_content += f'<p class="sub-title">{ch_sub_title}</p>'
                        html_content += '<p style="text-indent:0;">&nbsp;</p><p style="text-indent:0;">&nbsp;</p><p style="text-indent:0;">&nbsp;</p>'
                    else:
                        html_content += '<p style="text-indent:0;">&nbsp;</p><p style="text-indent:0;">&nbsp;</p><p style="text-indent:0;">&nbsp;</p>'
                    
                    prev_is_dialogue = None
                    prev_is_system = False
                    prev_is_chat = False
                    prev_is_game_chat = False
                    post_buffer = []
                    reply_buffer = []
                    is_collecting_post = False
                    is_collecting_reply = False
                    
                    for line in ch_lines:
                        if line == '* * *' or line.replace(' ', '') == '***':
                            if is_collecting_post and post_buffer:
                                html_content += f'<div class="board-post-box"><div class="board-post-title">{post_buffer[0]}</div><div class="board-post-content">{"<br/>".join(post_buffer[1:])}</div></div>'
                                post_buffer, is_collecting_post = [], False
                            if is_collecting_reply and reply_buffer:
                                html_content += '<div class="board-reply-container">'
                                for r in reply_buffer:
                                    html_content += f'<div class="board-reply-item"><span class="board-reply-author">{r.split(":",1)[0].strip()}</span>: {r.split(":",1)[1].strip()}</div>' if ":" in r else f'<div class="board-reply-item">{r}</div>'
                                html_content += '</div>'
                                reply_buffer, is_collecting_reply = [], False
                            html_content += '<p style="text-indent:0;">&nbsp;</p><p style="text-indent:0;">&nbsp;</p>'
                            html_content += f'<p class="scene-divider">{line}</p>'
                            html_content += '<p style="text-indent:0;">&nbsp;</p><p style="text-indent:0;">&nbsp;</p>'
                            prev_is_dialogue = None
                            prev_is_system = prev_is_chat = prev_is_game_chat = False
                            continue
                        
                        # 다중 기호 쌍 매칭 확인
                        match_post, p_s, p_e = check_match(line, use_board_post, final_post_pairs)
                        match_reply, r_s, r_e = check_match(line, use_board_post, final_reply_pairs)
                        match_game, g_s, g_e = check_match(line, use_game_chat, final_game_pairs)
                        match_chat, c_s, c_e = check_match(line, use_chat_window, final_chat_pairs)
                        match_sys, s_s, s_e = check_match(line, use_system_window, final_sys_pairs)

                        # 가. 게시글 감지
                        if match_post:
                            inner = line[len(p_s):-len(p_e)].strip()
                            if not is_collecting_post:
                                if is_collecting_reply and reply_buffer:
                                    html_content += '<div class="board-reply-container">'
                                    for r in reply_buffer: html_content += f'<div class="board-reply-item"><span class="board-reply-author">{r.split(":",1)[0].strip()}</span>: {r.split(":",1)[1].strip()}</div>' if ":" in r else f'<div class="board-reply-item">{r}</div>'
                                    html_content += '</div>'
                                    reply_buffer, is_collecting_reply = [], False
                                is_collecting_post = True
                                html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            post_buffer.append(inner)
                            prev_is_dialogue = None
                            prev_is_system = prev_is_chat = prev_is_game_chat = False
                            continue
                        
                        # 나. 댓글 감지
                        elif match_reply:
                            inner = line[len(r_s):-len(r_e)].strip()
                            if not is_collecting_reply:
                                if is_collecting_post and post_buffer:
                                    html_content += f'<div class="board-post-box"><div class="board-post-title">{post_buffer[0]}</div><div class="board-post-content">{"<br/>".join(post_buffer[1:])}</div></div>'
                                    post_buffer, is_collecting_post = [], False
                                is_collecting_reply = True
                                html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            reply_buffer.append(inner)
                            prev_is_dialogue = None
                            prev_is_system = prev_is_chat = prev_is_game_chat = False
                            continue
                        
                        # 다. 일반 라인 등장 시 모아둔 게시글/댓글 처리
                        else:
                            if is_collecting_post and post_buffer:
                                html_content += f'<div class="board-post-box"><div class="board-post-title">{post_buffer[0]}</div><div class="board-post-content">{"<br/>".join(post_buffer[1:])}</div></div>'
                                post_buffer, is_collecting_post = [], False
                                html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            if is_collecting_reply and reply_buffer:
                                html_content += '<div class="board-reply-container">'
                                for r in reply_buffer: html_content += f'<div class="board-reply-item"><span class="board-reply-author">{r.split(":",1)[0].strip()}</span>: {r.split(":",1)[1].strip()}</div>' if ":" in r else f'<div class="board-reply-item">{r}</div>'
                                html_content += '</div>'
                                reply_buffer, is_collecting_reply = [], False
                                html_content += '<p style="text-indent:0;">&nbsp;</p>'

                        # 라. 게임채팅 렌더링
                        if match_game:
                            if not prev_is_game_chat: html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            elif prev_is_game_chat: html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            inner = line[len(g_s):-len(g_e)].strip()
                            cc = "g-normal"
                            if inner.startswith("[길드]"): cc = "g-guild"
                            elif inner.startswith("[파티]"): cc = "g-party"
                            elif inner.startswith("[귓속말]") or inner.startswith("[귓]"): cc = "g-whisper"
                            elif inner.startswith("[시스템]") or inner.startswith("[공지]"): cc = "g-sys"
                            elif inner.startswith("[팀]"): cc = "g-team"
                            elif inner.startswith("[친구]") or inner.startswith("[친]"): cc = "g-friend"
                            html_content += f'<div class="game-chat-box {cc}">{inner}</div>'
                            prev_is_dialogue = None
                            prev_is_system = prev_is_chat = False
                            prev_is_game_chat = True
                            
                        # 마. 메신저창 렌더링
                        elif match_chat:
                            if prev_is_game_chat: html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            if not prev_is_chat: html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            inner = line[len(c_s):-len(c_e)].strip()
                            if ":" in inner:
                                s, c = inner.split(":", 1)
                                html_content += f'<div class="chat-other-block"><span class="chat-sender-name">{s.strip()}</span><span class="chat-bubble-other">{c.strip()}</span></div>'
                            else:
                                html_content += f'<div class="chat-my-block"><span class="chat-bubble-my">{inner}</span></div>'
                            prev_is_dialogue = None
                            prev_is_system = prev_is_game_chat = False
                            prev_is_chat = True
                            
                        # 바. 상태 시스템창 렌더링
                        elif match_sys:
                            if prev_is_chat or prev_is_game_chat: html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            html_content += f'<p class="system-box">{line}</p>'
                            prev_is_dialogue = None
                            prev_is_system = True
                            prev_is_chat = prev_is_game_chat = False
                        
                        # 사. 리얼 일반 본문 / 대사
                        else:
                            if prev_is_chat or prev_is_system or prev_is_game_chat: html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            is_d = line.startswith(dialogue_quotes) or line.startswith("-")
                            if dialogue_spacing_option and prev_is_dialogue is not None:
                                if not prev_is_dialogue and is_d: html_content += '<p style="text-indent:0;">&nbsp;</p>'
                                elif prev_is_dialogue and not is_d: html_content += '<p style="text-indent:0;">&nbsp;</p>'
                            html_content += f'<p>{line}</p>'
                            prev_is_dialogue = is_d
                            prev_is_system = prev_is_chat = prev_is_game_chat = False

                    # 루프 종료 버퍼 청소
                    if is_collecting_post and post_buffer:
                        html_content += f'<div class="board-post-box"><div class="board-post-title">{post_buffer[0]}</div><div class="board-post-content">{"<br/>".join(post_buffer[1:])}</div></div>'
                    if is_collecting_reply and reply_buffer:
                        html_content += '<div class="board-reply-container">'
                        for r in reply_buffer: html_content += f'<div class="board-reply-item"><span class="board-reply-author">{r.split(":",1)[0].strip()}</span>: {r.split(":",1)[1].strip()}</div>' if ":" in r else f'<div class="board-reply-item">{r}</div>'
                        html_content += '</div>'

                    html_content += '</body></html>'
                    chapter = epub.EpubHtml(title=display_title, file_name=f'chap_{i+1}.xhtml', lang='ko')
                    chapter.content = html_content
                    chapter.add_item(nav_css)
                    book.add_item(chapter)
                    epub_chapters.append(chapter)

                book.toc = tuple(epub_chapters)
                book.add_item(epub.EpubNcx()); book.add_item(epub.EpubNav()); book.spine = epub_chapters 
                epub_fp = io.BytesIO()
                epub.write_epub(epub_fp, book, {})
                epub_data = epub_fp.getvalue()

                st.success("🎉 변환 및 리스타일링 성공! 아래 버튼을 눌러 저장하세요.")
                st.download_button(label="📥 가공된 EPUB 파일 다운로드", data=epub_data, file_name=f"{title}.epub", mime="application/epub+zip", use_container_width=True)
            except Exception as e: st.error(f"오류가 발생했습니다: {e}")
else: st.info("파일 업로드 및 도서 정보를 모두 입력하시면 변환 버튼이 나타납니다.")
