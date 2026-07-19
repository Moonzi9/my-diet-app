import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import urllib.request
import os
import calendar as cal_module
import pandas as pd
from datetime import datetime

from config import MET_TABLE, CHARACTER_TYPES, CONDITION_OPTIONS, REASON_CATEGORIES, EXERCISE_EMOJIS, EXERCISE_VIDEOS, LEVEL_XP_PER_LEVEL, MILESTONE_THRESHOLDS, XP_RESIST, RARITY_BOOST, ITEM_EFFECT_DURATION_HOURS
from logic import (
    register_user, login_user, get_security_question, verify_and_show_pin, get_profile,
    do_search, parse_candidate, get_macros_for_row, calc_macro_ratio,
    calc_minutes, generate_comment, save_record,
    get_pet_status, check_attendance, get_inventory, get_period_records, get_monthly_calendar,
    generate_weight_progress_message,
    recognize_food_from_image, estimate_calorie_with_ai,
    equip_item, get_equipped_item, get_active_boost, log_bonus_xp, get_item_rarity,
    get_today_counts, check_daily_milestone,
    get_leaderboard, now_kst,
)
from PIL import Image

st.set_page_config(page_title="먹을까 말까", page_icon="🍪", layout="centered")

FONT_PATH = "NanumGothic.ttf"
if not os.path.isfile(FONT_PATH):
    try:
        urllib.request.urlretrieve(
            "https://raw.githubusercontent.com/google/fonts/main/ofl/nanumgothic/NanumGothic-Regular.ttf",
            FONT_PATH
        )
    except Exception:
        pass

if os.path.isfile(FONT_PATH):
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams['font.family'] = fm.FontProperties(fname=FONT_PATH).get_name()
plt.rcParams['axes.unicode_minus'] = False

# ---------- 세션 상태 초기화 ----------

if "page" not in st.session_state:
    query_nickname = st.query_params.get("user")
    restored = False
    if query_nickname:
        profile = get_profile(query_nickname)
        if profile:
            st.session_state.nickname = query_nickname
            st.session_state.goal_weight = profile["목표체중"]
            st.session_state.character = profile["캐릭터"]
            st.session_state.page = "main"
            restored = True
    if not restored:
        st.session_state.page = "login"
        st.session_state.nickname = ""
        st.session_state.goal_weight = None
        st.session_state.character = "강아지"

if "candidates" not in st.session_state:
    st.session_state.candidates = []
if "search_note" not in st.session_state:
    st.session_state.search_note = ""
if "food_cart" not in st.session_state:
    st.session_state.food_cart = []


def go(page):
    st.session_state.page = page
    st.rerun()


@st.dialog("음식 검색 결과")
def show_candidate_dialog(none_option):
    st.caption("스크롤해서 더 많은 결과를 확인하세요")
    with st.container(height=350):
        choice = st.radio(
            "검색 결과", st.session_state.candidates + [none_option],
            label_visibility="collapsed", key="dialog_radio"
        )
    if st.button("이걸로 선택", type="primary"):
        if choice == none_option:
            st.session_state.selected_candidate_value = None
            st.session_state.show_fallback_flag = True
        else:
            st.session_state.selected_candidate_value = choice
            st.session_state.show_fallback_flag = False
        st.rerun()


# ---------- 로그인 화면 ----------

def render_login():
    left, center, right = st.columns([1, 1.2, 1])
    with center:
        st.markdown("<div style='text-align:center; font-size:3rem; margin-top:60px;'>🍪</div>", unsafe_allow_html=True)
        st.markdown("<div style='text-align:center; font-size:1.5rem; font-weight:800;'>먹을까 말까</div>", unsafe_allow_html=True)
        st.markdown("<div style='text-align:center; color:#a0785a; font-size:0.9rem; margin-bottom:20px;'>참을까 말까 고민되는 순간, 함께해요</div>", unsafe_allow_html=True)
        st.markdown("<hr style='margin-bottom:20px;'>", unsafe_allow_html=True)

        nickname = st.text_input("닉네임", key="login_nickname")
        pin = st.text_input("PIN (숫자 4자리)", type="password", key="login_pin")

        if st.button("로그인", type="primary", use_container_width=True):
            profile, msg = login_user(nickname, pin)
            if profile:
                st.session_state.nickname = nickname
                st.session_state.goal_weight = profile["목표체중"]
                st.session_state.character = profile["캐릭터"]
                st.query_params["user"] = nickname
                go("main")
            else:
                st.warning(msg)

        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("회원가입", use_container_width=True):
                go("register")
        with col2:
            if st.button("PIN 찾기", use_container_width=True):
                go("find_pin")


# ---------- 회원가입 화면 ----------

def render_register():
    left, center, right = st.columns([1, 1.2, 1])
    with center:
        st.markdown("<div style='text-align:center; font-size:1.2rem; font-weight:bold; margin-top:40px; margin-bottom:16px;'>회원가입</div>", unsafe_allow_html=True)

        nickname = st.text_input("닉네임", key="reg_nickname")
        pin = st.text_input("PIN (숫자 4자리)", type="password", key="reg_pin")
        question = st.selectbox("보안질문", ["최애 음식은?", "가장 좋아하는 운동은?", "어릴 때 별명은?"])
        answer = st.text_input("답변", key="reg_answer")
        goal_weight = st.number_input("목표 체중(kg)", min_value=0.0, value=None)
        character_type = st.selectbox("키울 캐릭터를 골라주세요", list(CHARACTER_TYPES.keys()))
        st.caption("".join(CHARACTER_TYPES[character_type]) + "  ← 이렇게 자라나요")

        if st.button("가입하기", type="primary", use_container_width=True):
            msg = register_user(nickname, pin, question, answer, goal_weight, character_type)
            st.info(msg)

        if st.button("← 로그인으로 돌아가기", use_container_width=True):
            go("login")


# ---------- PIN 찾기 화면 ----------

def render_find_pin():
    left, center, right = st.columns([1, 1.2, 1])
    with center:
        st.markdown("<div style='text-align:center; font-size:1.2rem; font-weight:bold; margin-top:40px; margin-bottom:16px;'>PIN 찾기</div>", unsafe_allow_html=True)

        nickname = st.text_input("닉네임", key="find_nickname")

        if st.button("보안질문 확인", use_container_width=True):
            question, msg = get_security_question(nickname)
            st.session_state.find_question = question
            if msg:
                st.warning(msg)

        if st.session_state.get("find_question"):
            st.markdown(f"**질문: {st.session_state.find_question}**")
            answer = st.text_input("답변", key="find_answer")
            if st.button("확인", type="primary", use_container_width=True):
                result = verify_and_show_pin(nickname, answer)
                st.info(result)

        if st.button("← 로그인으로 돌아가기", use_container_width=True):
            go("login")


# ---------- 메인 화면 ----------

def render_main():
    nickname = st.session_state.nickname
    header_col, logout_col = st.columns([4, 1])
    with header_col:
        st.markdown(f"### 🍪 먹을까 말까 — {nickname}님")
    with logout_col:
        if st.button("로그아웃"):
            st.query_params.clear()
            st.session_state.page = "login"
            st.session_state.nickname = ""
            st.rerun()

    tab1, tab2, tab3 = st.tabs(["🍪 먹을까 말까", "기록 보기", "🏆 랭킹"])

    with tab1:
        level, xp, remaining, emoji, stage_name, equipped_name, equipped_rarity, boost_ratio, hours_left = get_pet_status(nickname, st.session_state.character)
        resist_today, ate_today = get_today_counts(nickname)

        char_col, counter_col = st.columns([2, 1])

        with char_col:
            item_emoji = equipped_name.split(" ")[0] if equipped_name else ""
            overlay_html = (
                f"<div style='position:absolute; top:-18px; left:50%; transform:translateX(-50%) rotate(-10deg); font-size:2.2rem;'>{item_emoji}</div>"
                if item_emoji else ""
            )

            st.markdown(
                f"<div style='position:relative; width:140px; margin:0 auto; text-align:center;'>"
                f"{overlay_html}"
                f"<div style='font-size:5rem;'>{emoji}</div>"
                f"</div>",
                unsafe_allow_html=True
            )
            st.markdown(f"<div style='text-align:center; font-weight:bold; margin-top:2px;'>Lv.{level} · {stage_name}</div>", unsafe_allow_html=True)
            if equipped_name:
                if boost_ratio > 0:
                    st.markdown(
                        f"<div style='text-align:center; color:#888; font-size:0.8rem;'>"
                        f"{equipped_name} 착용 중 · 참음 XP +{int(boost_ratio*100)}% · {hours_left}시간 남음</div>",
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(f"<div style='text-align:center; color:#888; font-size:0.8rem;'>{equipped_name} 착용 중 (효과 만료)</div>", unsafe_allow_html=True)

        with counter_col:
            st.markdown(
                f"<div style='background:#FFF8F0; border:1px solid #FFE0C2; border-radius:12px; padding:14px; margin-top:20px;'>"
                f"<div style='font-size:0.85rem; color:#a0785a;'>오늘의 활동</div>"
                f"<div style='font-size:1.3rem; font-weight:bold; color:#6BCB77;'>💪 참음 {resist_today}회</div>"
                f"<div style='font-size:1.3rem; font-weight:bold; color:#FF6B6B;'>🔥 먹음 {ate_today}회</div>"
                f"</div>",
                unsafe_allow_html=True
            )
            next_milestone = next((m for m in MILESTONE_THRESHOLDS if m > resist_today), None)
            if next_milestone:
                st.caption(f"다음 보너스까지 참음 {next_milestone - resist_today}회 남음")

        progress_ratio = (xp % LEVEL_XP_PER_LEVEL) / LEVEL_XP_PER_LEVEL
        st.progress(progress_ratio)
        st.caption(f"누적 경험치 {xp} XP · 다음 레벨까지 {remaining} XP 남았어요")

        if st.button("📅 오늘 출석체크"):
            msg = check_attendance(nickname)
            st.info(msg)

        inventory = get_inventory(nickname)
        if inventory:
            item_labels = [f"{item} x{count}" for item, count in inventory.items()]
            st.markdown("**보유 아이템**  " + "  ".join(item_labels))

            equip_choice = st.selectbox("파트너에게 적용할 아이템", list(inventory.keys()))
            preview_rarity = get_item_rarity(equip_choice)
            preview_boost = RARITY_BOOST.get(preview_rarity, 0.0)
            st.caption(f"효과: 참음 XP +{int(preview_boost*100)}% · {ITEM_EFFECT_DURATION_HOURS}시간 지속")
            if st.button("✨ 캐릭터에게 적용"):
                equip_item(nickname, equip_choice)
                st.success(f"{equip_choice}을(를) 적용했어요!")
                st.rerun()
        else:
            st.caption("아직 획득한 아이템이 없어요. 출석체크를 해보세요!")

        st.markdown("---")

        search_col, camera_col = st.columns([5, 1])
        with search_col:
            query = st.text_input("음식 검색", placeholder="예: 떡볶이, 라면")
        with camera_col:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            with st.popover("📷"):
                uploaded_image = st.file_uploader("음식 사진 첨부", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
                if uploaded_image is not None and st.button("인식하기"):
                    image = Image.open(uploaded_image)
                    with st.spinner("음식 인식 중..."):
                        recognized = recognize_food_from_image(image)
                    if recognized:
                        st.success(f"인식된 음식: {recognized}")
                        candidates, note = do_search(recognized)
                        st.session_state.candidates = candidates
                        st.session_state.search_note = note
                        st.session_state.recognized_name = recognized
                        st.session_state.search_query = recognized
                        st.rerun()
                    else:
                        st.warning("음식을 인식하지 못했어요.")

        if st.button("🔍 검색"):
            candidates, note = do_search(query)
            st.session_state.candidates = candidates
            st.session_state.search_note = note
            st.session_state.search_query = query
            st.session_state.selected_candidate_value = None
            st.session_state.show_fallback_flag = False

        if st.session_state.search_note:
            st.caption(st.session_state.search_note)

        selected_candidate = st.session_state.get("selected_candidate_value")
        manual_name = ""
        manual_kcal = None
        show_fallback = st.session_state.get("show_fallback_flag", False)
        NONE_OF_THESE = "🔍 원하는 게 없어요 (직접입력/AI추정)"

        if st.session_state.candidates:
            if selected_candidate:
                st.success(f"✅ 선택됨: {selected_candidate}")
            if st.button(f"🔽 검색 결과 보기 ({len(st.session_state.candidates)}개)"):
                show_candidate_dialog(NONE_OF_THESE)
        elif st.session_state.search_note:
            show_fallback = True

        if show_fallback:
            ai_guess_target = st.session_state.get("recognized_name") or query
            if st.button(f"🤖 AI에게 '{ai_guess_target}' 칼로리 추정 받기"):
                estimate = estimate_calorie_with_ai(ai_guess_target)
                if estimate:
                    st.session_state.ai_estimate = estimate
                    st.session_state.ai_estimate_name = ai_guess_target
                    st.info(f"AI 추정치 (1인분 기준): {estimate['칼로리']}kcal (탄 {estimate['탄수화물']}g · 단 {estimate['단백질']}g · 지 {estimate['지방']}g)\n\n⚠️ 정확한 데이터가 아닌 AI의 일반 상식 기반 추정치예요")
                else:
                    st.warning("추정에 실패했어요. 이름과 칼로리를 직접 입력해주세요.")

            manual_name = st.text_input("음식 이름 직접 입력", value=st.session_state.get("ai_estimate_name", ""))
            manual_kcal = st.number_input(
                "칼로리(kcal) 직접 입력",
                min_value=0.0,
                value=st.session_state.get("ai_estimate", {}).get("칼로리")
            )

        unit = "g"
        if selected_candidate:
            _, _, _basis = parse_candidate(selected_candidate)
            if _basis and "ml" in _basis:
                unit = "ml"

        amount_g = st.number_input(f"섭취량({unit})", min_value=0.0, value=100.0,
                                     help=f"100{unit} 기준 검색결과를 이 양만큼 환산해요 (직접입력엔 적용 안 됨)")

        def resolve_current_selection():
            if selected_candidate:
                base_name, base_kcal, basis = parse_candidate(selected_candidate)
                carb0, protein0, fat0 = get_macros_for_row(base_name)
                ratio = amount_g / 100
                item_calorie = round(base_kcal * ratio, 1)
                item_carb = round(carb0 * ratio, 1)
                item_protein = round(protein0 * ratio, 1)
                item_fat = round(fat0 * ratio, 1)
                shown_name = st.session_state.get("search_query") or base_name
                item_name = f"{shown_name} ({amount_g}{'ml' if 'ml' in basis else 'g'})"
                item_note = f"⚠️ {shown_name}: 원래 기준량이 {basis}이라 g 환산이 정확하지 않을 수 있어요" if "100g" not in basis else ""
                return {"name": item_name, "calorie": item_calorie, "carb": item_carb,
                        "protein": item_protein, "fat": item_fat, "is_manual": False, "note": item_note}
            elif manual_name and manual_kcal is not None:
                ai_est = st.session_state.get("ai_estimate")
                ai_name = st.session_state.get("ai_estimate_name")
                if ai_est and manual_name == ai_name:
                    item_carb = ai_est.get("탄수화물", 0)
                    item_protein = ai_est.get("단백질", 0)
                    item_fat = ai_est.get("지방", 0)
                    item_note = ""
                    has_macro_data = True
                else:
                    item_carb = item_protein = item_fat = 0
                    item_note = f"⚠️ {manual_name}: 탄단지 정보 없음(직접입력)"
                    has_macro_data = False
                return {"name": manual_name, "calorie": manual_kcal, "carb": item_carb, "protein": item_protein,
                        "fat": item_fat, "is_manual": not has_macro_data, "note": item_note}
            return None

        def clear_search_state():
            st.session_state.candidates = []
            st.session_state.search_note = ""
            st.session_state.selected_candidate_value = None
            st.session_state.show_fallback_flag = False
            st.session_state.search_query = ""
            for k in ["ai_estimate", "ai_estimate_name", "recognized_name"]:
                st.session_state.pop(k, None)

        if st.button("🛒 장바구니에 담기"):
            resolved = resolve_current_selection()
            if resolved:
                st.session_state.food_cart.append(resolved)
                clear_search_state()
                st.rerun()
            else:
                st.warning("⚠️ 검색 결과에서 선택하거나, 이름+칼로리를 직접 입력해주세요.")

        if st.session_state.food_cart:
            st.markdown("#### 🛒 담은 음식")
            cart_total = sum(item["calorie"] for item in st.session_state.food_cart)
            for i, item in enumerate(st.session_state.food_cart):
                c_left, c_right = st.columns([5, 1])
                c_left.markdown(f"- {item['name']} — {item['calorie']}kcal")
                if c_right.button("❌", key=f"remove_cart_{i}"):
                    st.session_state.food_cart.pop(i)
                    st.rerun()
            st.markdown(f"**합계: {cart_total}kcal**")
            st.caption("여러 음식을 계속 검색해서 담을 수 있어요 (예: 치킨 + 제로콜라)")

        weight_kg = st.number_input("오늘 체중(kg)", min_value=0.0,
                                      value=None, key="main_weight")
        exercise = st.selectbox(
            "운동 종류",
            options=[None] + list(MET_TABLE.keys()),
            format_func=lambda x: f"{EXERCISE_EMOJIS.get(x, '')} {x}" if x else "선택하세요"
        )
        condition_choice = st.radio(
            "오늘 컨디션",
            CONDITION_OPTIONS,
            format_func=lambda x: f"{x[0]} {x[1]}",
            horizontal=True,
        )
        condition = condition_choice[1]
        reason_choice = st.radio("왜 먹고 싶어요?", REASON_CATEGORIES + ["기타(직접입력)"], horizontal=True)
        if reason_choice == "기타(직접입력)":
            reason = st.text_input("이유를 직접 입력해주세요", placeholder="예: 시험 끝나서")
        else:
            reason = reason_choice
        mode = st.radio("코멘트 톤", ["재치", "진지"], horizontal=True)

        col1, col2 = st.columns(2)
        with col1:
            ate_clicked = st.button("먹었어요 😋", use_container_width=True)
        with col2:
            resist_clicked = st.button("참았어요 💪", use_container_width=True)

        if ate_clicked or resist_clicked:
            ate = ate_clicked
            if weight_kg is None:
                st.warning("⚠️ 체중을 입력해주세요.")
            elif not exercise:
                st.warning("⚠️ 운동 종류를 선택해주세요.")
            else:
                items = list(st.session_state.food_cart)
                current = resolve_current_selection()
                if current:
                    items.append(current)

                if not items:
                    st.warning("⚠️ 음식을 검색해서 장바구니에 담거나, 이름+칼로리를 직접 입력해주세요.")
                else:
                    display_name = ", ".join(item["name"] for item in items)
                    calorie = round(sum(item["calorie"] for item in items), 1)
                    carb = round(sum(item["carb"] for item in items), 1)
                    protein = round(sum(item["protein"] for item in items), 1)
                    fat = round(sum(item["fat"] for item in items), 1)
                    has_any_macro_data = any(not item["is_manual"] for item in items)
                    has_missing_macro_data = any(item["is_manual"] for item in items)
                    basis_note = " / ".join(item["note"] for item in items if item["note"])

                    minutes = calc_minutes(calorie, exercise, weight_kg)
                    comment = generate_comment(reason, display_name, calorie, exercise, minutes, ate, mode)
                    save_record(nickname, display_name, calorie, ate, reason,
                                reason, exercise, minutes, comment)

                    st.session_state.food_cart = []
                    clear_search_state()

                    milestone_result = check_daily_milestone(nickname) if not ate else None

                    bonus_earned = 0
                    if not ate:
                        active_boost_ratio, _, _ = get_active_boost(nickname)
                        if active_boost_ratio > 0:
                            bonus_earned = round(XP_RESIST * active_boost_ratio)
                            log_bonus_xp(nickname, bonus_earned)

                    carb_p, protein_p, fat_p = calc_macro_ratio(carb, protein, fat)

                    st.markdown("---")
                    st.markdown(f"#### 📍 {display_name}")
                    st.markdown(f"## {calorie} kcal")
                    if basis_note:
                        st.caption(basis_note)

                    if bonus_earned > 0:
                        st.info(f"✨ 아이템 효과로 보너스 XP +{bonus_earned}을(를) 추가로 받았어요!")

                    if milestone_result:
                        milestone_count, milestone_item = milestone_result
                        st.balloons()
                        st.success(f"🎊 오늘 {milestone_count}번째 참음 달성! **레전드 등급** 보너스 아이템 {milestone_item}을(를) 획득했어요!")

                    if has_any_macro_data:
                        c1, c2, c3 = st.columns(3)
                        c1.metric("탄수화물", f"{carb}g", f"{int(carb_p*100)}%")
                        c2.metric("단백질", f"{protein}g", f"{int(protein_p*100)}%")
                        c3.metric("지방", f"{fat}g", f"{int(fat_p*100)}%")
                        if has_missing_macro_data:
                            st.caption("⚠️ 일부 음식은 탄단지 정보가 없어 합계에서 제외됐어요 (칼로리만 반영)")

                    st.markdown(f"{EXERCISE_EMOJIS.get(exercise, '🏃')} **{exercise}** 기준 **{minutes}분**")
                    st.markdown(f"🧘 오늘 컨디션: {condition_choice[0]} {condition}")
                    st.markdown(f"📂 유혹 이유: {reason}")
                    st.markdown("---")
                    st.markdown(f"🤖 {comment}")

                    goal_msg, remaining_kg = generate_weight_progress_message(
                        weight_kg, st.session_state.goal_weight, ate
                    )
                    st.markdown("---")
                    if remaining_kg > 0:
                        st.markdown(f"🎯 목표까지 **{remaining_kg}kg** 남았어요")
                    st.markdown(f"{'🔥' if ate else '💪'} {goal_msg}")

                    if ate:
                        st.markdown("---")
                        st.markdown("🎥 오늘의 추천 운동 영상")
                        video_url = EXERCISE_VIDEOS.get(exercise)
                        if video_url:
                            st.video(video_url)
                        search_url = f"https://www.youtube.com/results?search_query={exercise}+홈트+초보"
                        st.caption(f"영상이 재생되지 않으면 [여기서 직접 찾아보기]({search_url})")

    with tab2:
        period = st.radio("조회 기간", ["이번 주", "이번 달"], horizontal=True)
        if st.button("🔄 조회"):
            df, stats = get_period_records(period, nickname)
            if isinstance(stats, dict):
                st.markdown(f"### 📊 {period} 요약 ({nickname}님)")

                m1, m2, m3 = st.columns(3)
                m1.metric("총 기록", f"{stats['총 기록']}건")
                m2.metric("참음", f"{stats['참음']}회", delta=f"-{stats['먹음']}회 먹음", delta_color="off")
                m3.metric("최장 스트릭", f"{stats['최장 스트릭']}일")

                st.markdown(
                    f"<div style='display:flex; gap:12px; margin-top:8px;'>"
                    f"<div style='flex:1; background:#FFF8F0; border:1px solid #FFE0C2; border-radius:10px; padding:10px; text-align:center;'>"
                    f"<div style='font-size:0.8rem; color:#a0785a;'>가장 많이 마주친 음식</div>"
                    f"<div style='font-weight:bold;'>🍽️ {stats['자주 마주친 음식']}</div>"
                    f"</div>"
                    f"<div style='flex:1; background:#F5F5FF; border:1px solid #DCDCFF; border-radius:10px; padding:10px; text-align:center;'>"
                    f"<div style='font-size:0.8rem; color:#6a6a9a;'>가장 많은 유혹 이유</div>"
                    f"<div style='font-weight:bold;'>💭 {stats['가장 많은 유혹 이유']}</div>"
                    f"</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )

                if period == "이번 달":
                    st.markdown("#### 📅 이번 달 캘린더")
                    calendar_data = get_monthly_calendar(nickname)
                    now = now_kst()
                    cal = cal_module.Calendar(firstweekday=6)
                    month_days = cal.monthdayscalendar(now.year, now.month)
                    weekday_names = ["일", "월", "화", "수", "목", "금", "토"]

                    html = "<table style='width:100%; text-align:center; border-collapse:collapse;'>"
                    html += "<tr>" + "".join(f"<th style='padding:4px; color:#888;'>{d}</th>" for d in weekday_names) + "</tr>"
                    for week in month_days:
                        html += "<tr>"
                        for day in week:
                            if day == 0:
                                html += "<td style='padding:8px;'></td>"
                            else:
                                info = calendar_data.get(day)
                                if info and (info["참음"] or info["먹음"]):
                                    resist, ate = info["참음"], info["먹음"]
                                    bg = "#E8F8EE" if resist >= ate else "#FFEAEA"
                                    detail = (f"💪{resist} " if resist else "") + (f"🔥{ate}" if ate else "")
                                    html += (f"<td style='background:{bg}; border-radius:8px; padding:6px; "
                                             f"vertical-align:top;'><b>{day}</b><br>"
                                             f"<span style='font-size:0.7rem;'>{detail}</span></td>")
                                else:
                                    html += f"<td style='padding:6px; color:#ccc;'>{day}</td>"
                        html += "</tr>"
                    html += "</table>"
                    st.markdown(html, unsafe_allow_html=True)
                    st.caption("🟢 참음이 더 많은 날 · 🔴 먹음이 더 많은 날")

                col1, col2 = st.columns(2)
                with col1:
                    fig1, ax1 = plt.subplots()
                    ate_counts = df["먹음여부"].value_counts()
                    color_map = {True: "#FF6B6B", False: "#6BCB77"}
                    labels1 = ["먹음" if v else "참음" for v in ate_counts.index]
                    colors1 = [color_map[v] for v in ate_counts.index]
                    ax1.pie(ate_counts.values, labels=labels1, autopct="%1.0f%%", colors=colors1)
                    ax1.set_title("먹음 vs 참음 비율")
                    st.pyplot(fig1)

                with col2:
                    fig2, ax2 = plt.subplots()
                    reason_counts = df["이유카테고리"].value_counts()
                    ax2.pie(reason_counts.values, labels=reason_counts.index, autopct="%1.0f%%")
                    ax2.set_title("유혹 이유 분포")
                    st.pyplot(fig2)

                st.dataframe(df, use_container_width=True)
            else:
                st.info(stats)

    with tab3:
        st.markdown("### 🏆 랭킹")
        st.caption("주간 랭킹이에요 · 매주 월요일 00:00(한국 시간) 기준으로 초기화돼요")

        board = get_leaderboard()
        if not board:
            st.info("아직 랭킹에 표시할 사용자가 없어요.")
        else:
            rank_icons = ["🥇", "🥈", "🥉"]
            table_rows = []
            for i, row in enumerate(board):
                rank = rank_icons[i] if i < 3 else f"{i+1}"
                table_rows.append({
                    "순위": rank,
                    "캐릭터": row["이모지"],
                    "닉네임": row["닉네임"],
                    "레벨": row["레벨"],
                    "XP": row["XP"],
                })
            board_df = pd.DataFrame(table_rows)

            def highlight_me(row):
                if row["닉네임"] == nickname:
                    return ["font-weight: bold; background-color: #FFF3CD"] * len(row)
                return [""] * len(row)

            styled_df = board_df.style.apply(highlight_me, axis=1)
            st.dataframe(
                styled_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "순위": st.column_config.TextColumn(width="small"),
                }
            )


# ---------- 라우팅 ----------

if st.session_state.page == "login":
    render_login()
elif st.session_state.page == "register":
    render_register()
elif st.session_state.page == "find_pin":
    render_find_pin()
elif st.session_state.page == "main":
    render_main()
