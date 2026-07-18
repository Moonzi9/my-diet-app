import os
import re
import random
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

def now_kst():
    return datetime.now(KST).replace(tzinfo=None)

import pandas as pd

from config import (
    model, food_df, CSV_FILE, PROFILE_FILE, ATTENDANCE_FILE, EQUIPPED_FILE,
    MILESTONE_FILE, MILESTONE_THRESHOLDS,
    BONUS_XP_FILE, ITEM_EFFECT_DURATION_HOURS, RARITY_BOOST,
    MET_TABLE, XP_RESIST, XP_ATE, LEVEL_XP_PER_LEVEL,
    ITEM_POOL, MILESTONE_ITEM_POOL, FALLBACK_COMMENTS_RESIST, FALLBACK_COMMENTS_ATE,
    CHARACTER_TYPES, STAGE_NAMES,
)

# ---------- Gemini 호출 ----------

def call_gemini_with_retry(prompt, generation_config=None, max_retries=1):
    for attempt in range(max_retries):
        try:
            if generation_config:
                return model.generate_content(prompt, generation_config=generation_config)
            return model.generate_content(prompt)
        except Exception as e:
            if "429" in str(e):
                return None
            raise
    return None

# ---------- 회원가입/로그인/PIN찾기 ----------

def get_profile(nickname):
    if not os.path.isfile(PROFILE_FILE):
        return None
    df = pd.read_csv(PROFILE_FILE, encoding="utf-8-sig", dtype={"PIN": str})
    matched = df[df["닉네임"] == nickname]
    if len(matched) == 0:
        return None
    row = matched.iloc[0]
    return {
        "닉네임": row["닉네임"],
        "PIN": str(row["PIN"]).strip(),
        "보안질문": row["보안질문"],
        "보안답변": row["보안답변"],
        "목표체중": float(row["목표체중"]),
        "캐릭터": row["캐릭터"]
    }

NICKNAME_PATTERN = re.compile(r"^[가-힣a-zA-Z0-9]{2,10}$")

def register_user(nickname, pin, question, answer, goal_weight, character_type):
    if not nickname or not pin or not answer or goal_weight is None or not character_type:
        return "⚠️ 모든 항목을 입력해주세요."
    nickname = nickname.strip()
    if not NICKNAME_PATTERN.match(nickname):
        return "⚠️ 닉네임은 한글/영문/숫자만 사용해서 2~10자로 입력해주세요. (띄어쓰기, 특수문자, 이모지 불가)"
    if len(pin) != 4 or not pin.isdigit():
        return "⚠️ PIN은 숫자 4자리로 입력해주세요."
    if get_profile(nickname):
        return "⚠️ 이미 있는 닉네임이에요. 다른 닉네임을 써주세요."

    if os.path.isfile(PROFILE_FILE):
        df = pd.read_csv(PROFILE_FILE, encoding="utf-8-sig", dtype={"PIN": str})
    else:
        df = pd.DataFrame(columns=["닉네임", "PIN", "보안질문", "보안답변", "목표체중", "캐릭터"])

    new_row = pd.DataFrame([{
        "닉네임": nickname, "PIN": pin, "보안질문": question,
        "보안답변": answer, "목표체중": goal_weight, "캐릭터": character_type
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(PROFILE_FILE, index=False, encoding="utf-8-sig")
    return f"✅ '{nickname}'님 가입 완료! 이제 로그인해주세요."

def login_user(nickname, pin):
    profile = get_profile(nickname)
    if profile is None:
        return None, "⚠️ 존재하지 않는 닉네임이에요."
    if profile["PIN"] != pin:
        return None, "⚠️ PIN이 일치하지 않아요."
    return profile, f"'{nickname}'님 환영해요! 😊"

def get_security_question(nickname):
    profile = get_profile(nickname)
    if profile is None:
        return None, "⚠️ 존재하지 않는 닉네임이에요."
    return profile["보안질문"], ""

def verify_and_show_pin(nickname, answer):
    profile = get_profile(nickname)
    if profile is None:
        return "⚠️ 존재하지 않는 닉네임이에요."
    if profile["보안답변"].strip() != answer.strip():
        return "⚠️ 답변이 일치하지 않아요."
    return f"🔑 회원님의 PIN은 [{profile['PIN']}]입니다."

# ---------- 음식명 정제 ----------

def normalize_food_name(user_input):
    prompt = f"""
사용자가 입력한 음식 표현: "{user_input}"

수량 표현(반마리, 곱빼기, 1인분 등)과 캐주얼한 말투(ㅋㅋ, 시켰음 등)만 제거하고,
음식의 구체적인 종류를 나타내는 단어는 절대 지우거나 뭉뚱그리지 마.

예시)
입력: "국물떡볶이 곱빼기" -> 출력: 국물떡볶이
입력: "후라이드 반마리" -> 출력: 후라이드치킨
입력: "치킨 한마리 시켰음ㅋㅋ" -> 출력: 치킨

다른 설명 없이 음식명만 출력해줘.
"""
    response = call_gemini_with_retry(prompt, generation_config={"temperature": 0})
    if response is None:
        return user_input
    return response.text.strip()

# ---------- 음식 검색 ----------

def search_food_candidates(query):
    if not query:
        return []
    matched = food_df[food_df["식품명"].str.contains(query, na=False)].copy()
    matched = matched[matched["에너지(kcal)"].notna()]
    if len(matched) == 0:
        return []
    matched = matched.sort_values("에너지(kcal)").head(15)
    candidates = []
    for _, row in matched.iterrows():
        candidates.append(f"{row['식품명']} ({row['에너지(kcal)']}kcal/{row['영양성분함량기준량']})")
    return candidates

def do_search(query):
    candidates = search_food_candidates(query)
    used_query = query

    if not candidates:
        normalized = normalize_food_name(query)
        if normalized and normalized != query:
            candidates = search_food_candidates(normalized)
            used_query = normalized

    if candidates:
        note = "" if used_query == query else f"'{query}' → '{used_query}'(으)로 바꿔서 검색했어요"
        return candidates, note
    return [], f"'{query}' 검색 결과가 없어요. 이름과 칼로리를 직접 입력해주세요."

def parse_candidate(candidate_str):
    m = re.match(r"^(.*) \(([\d.]+)kcal/(.+)\)$", candidate_str)
    if not m:
        return None, None, None
    return m.group(1), float(m.group(2)), m.group(3)

def calc_macro_ratio(carb_g, protein_g, fat_g):
    carb_kcal = carb_g * 4
    protein_kcal = protein_g * 4
    fat_kcal = fat_g * 9
    total = carb_kcal + protein_kcal + fat_kcal
    if total == 0:
        return 0, 0, 0
    return round(carb_kcal / total, 2), round(protein_kcal / total, 2), round(fat_kcal / total, 2)

def get_macros_for_row(food_name):
    nutrient_cols = ["탄수화물(g)", "단백질(g)", "지방(g)"]
    matched = food_df[food_df["식품명"] == food_name]
    if len(matched) == 0:
        return 0, 0, 0
    row = matched.iloc[0][nutrient_cols]
    carb = row["탄수화물(g)"]
    protein = row["단백질(g)"]
    fat = row["지방(g)"]
    carb = 0 if pd.isna(carb) else round(carb, 1)
    protein = 0 if pd.isna(protein) else round(protein, 1)
    fat = 0 if pd.isna(fat) else round(fat, 1)
    return carb, protein, fat

def recognize_food_from_image(image):
    prompt = """
이 이미지에 있는 음식이 뭔지 알려줘.
브랜드/프랜차이즈 메뉴라면 (예: BBQ 뿌링클, 교촌 허니콤보) 그 이름 그대로 알려줘.
가장 대표적인 한국어 음식명 하나만 딱 출력해줘.
음식이 명확하지 않거나 여러 개 섞여있으면 "인식불가"라고만 출력해줘.
다른 설명 없이 음식명만 출력해줘.
"""
    try:
        result = model.generate_content([prompt, image]).text.strip()
    except Exception:
        return None
    return None if result == "인식불가" else result

def estimate_calorie_with_ai(food_name):
    prompt = f"""
'{food_name}'의 실제로 알려진 영양정보(제품 포장지, 공식 홈페이지 등에서 흔히 표기되는 정보)를 기준으로,
일반적인 1인분(제공량) 기준 칼로리, 탄수화물(g), 단백질(g), 지방(g)을 추정해줘.
정확한 실시간 데이터가 아니라 알고 있는 지식 기반의 추정치임을 감안해줘.
잘 모르는 음식이면 비슷한 종류의 평균적인 값으로 추정해줘.

숫자만, 단위(kcal, g 등) 없이 순수 숫자로만 답해줘.
천단위 구분 쉼표는 절대 넣지 마 (예: 2100은 "2100"으로, "2,100"으로 쓰지 마).

아래 형식 그대로 딱 한 줄만 출력해줘 (다른 설명, 단위, 텍스트 없이 숫자와 쉼표만):
칼로리,탄수화물,단백질,지방

예시)
질문: '진라면 순한맛' -> 답: 500,79,10,14
질문: '초코파이 1개' -> 답: 130,20,1.5,4.5
질문: '뿌링클(순살, 한마리)' -> 답: 2100,150,120,110
"""
    response = call_gemini_with_retry(prompt, generation_config={"temperature": 0})
    if response is None:
        return None
    try:
        numbers = re.findall(r"\d+\.?\d*", response.text)
        if len(numbers) < 4:
            return None
        calorie, carb, protein, fat = [float(n) for n in numbers[:4]]
        if calorie <= 0 or calorie > 5000:
            return None
        return {"칼로리": calorie, "탄수화물": carb, "단백질": protein, "지방": fat}
    except Exception:
        return None

# ---------- 운동 환산 ----------

def calc_minutes(calorie, exercise, weight_kg):
    met = MET_TABLE[exercise]
    kcal_per_min = met * 3.5 * weight_kg / 200
    return round(calorie / kcal_per_min, 1)

# ---------- 기록/레벨 (닉네임별) ----------

def save_record(nickname, food_name, calorie, ate, reason_text, reason_category, exercise, minutes, comment):
    if os.path.isfile(CSV_FILE):
        df = pd.read_csv(CSV_FILE, encoding="utf-8-sig")
    else:
        df = pd.DataFrame(columns=["닉네임", "날짜시간", "음식명", "칼로리", "먹음여부", "유혹이유",
                                     "이유카테고리", "환산운동", "필요시간(분)", "스트릭", "AI코멘트"])

    user_df = df[df["닉네임"] == nickname]
    prev_streak = 0
    for ate_flag in reversed(user_df["먹음여부"].tolist()):
        if ate_flag == False:
            prev_streak += 1
        else:
            break
    new_streak = 0 if ate else prev_streak + 1

    new_row = pd.DataFrame([{
        "닉네임": nickname,
        "날짜시간": now_kst().strftime("%Y-%m-%d %H:%M"),
        "음식명": food_name,
        "칼로리": calorie,
        "먹음여부": ate,
        "유혹이유": reason_text,
        "이유카테고리": reason_category,
        "환산운동": exercise,
        "필요시간(분)": minutes,
        "스트릭": new_streak,
        "AI코멘트": comment.replace("\n", " ")
    }])
    new_row.to_csv(CSV_FILE, mode="a" if os.path.isfile(CSV_FILE) else "w",
                    header=not os.path.isfile(CSV_FILE), index=False, encoding="utf-8-sig")
    return new_streak

def get_today_counts(nickname):
    if not os.path.isfile(CSV_FILE) or not nickname:
        return 0, 0
    df = pd.read_csv(CSV_FILE, encoding="utf-8-sig")
    today = now_kst().strftime("%Y-%m-%d")
    user_df = df[(df["닉네임"] == nickname) & (df["날짜시간"].str.startswith(today))]
    resist_today = int((user_df["먹음여부"] == False).sum())
    ate_today = int((user_df["먹음여부"] == True).sum())
    return resist_today, ate_today

def check_daily_milestone(nickname):
    resist_today, _ = get_today_counts(nickname)
    if resist_today not in MILESTONE_THRESHOLDS:
        return None

    today = now_kst().strftime("%Y-%m-%d")
    if os.path.isfile(MILESTONE_FILE):
        df = pd.read_csv(MILESTONE_FILE, encoding="utf-8-sig")
        already = len(df[(df["닉네임"] == nickname) & (df["날짜"] == today) & (df["마일스톤"] == resist_today)]) > 0
        if already:
            return None
    else:
        df = pd.DataFrame(columns=["닉네임", "날짜", "마일스톤", "아이템"])

    emoji, name, rarity = random.choice(MILESTONE_ITEM_POOL)
    item_str = f"{emoji} {name}"
    new_row = pd.DataFrame([{"닉네임": nickname, "날짜": today, "마일스톤": resist_today, "아이템": item_str}])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(MILESTONE_FILE, index=False, encoding="utf-8-sig")
    return resist_today, item_str

def get_leaderboard(top_n=10):
    if not os.path.isfile(PROFILE_FILE):
        return []
    profiles = pd.read_csv(PROFILE_FILE, encoding="utf-8-sig", dtype={"PIN": str})

    now = now_kst()
    week_start = now - pd.Timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

    if not os.path.isfile(CSV_FILE):
        records = pd.DataFrame(columns=["닉네임", "먹음여부", "날짜시간"])
    else:
        records = pd.read_csv(CSV_FILE, encoding="utf-8-sig")
        records["날짜시간"] = pd.to_datetime(records["날짜시간"])
        records = records[records["날짜시간"] >= week_start]

    rows = []
    for _, row in profiles.iterrows():
        nickname = row["닉네임"]
        character = row["캐릭터"]
        user_records = records[records["닉네임"] == nickname]
        resist_count = int((user_records["먹음여부"] == False).sum())
        ate_count = int((user_records["먹음여부"] == True).sum())
        xp = resist_count * XP_RESIST + ate_count * XP_ATE
        level = xp // LEVEL_XP_PER_LEVEL + 1
        emoji_list = CHARACTER_TYPES.get(character, CHARACTER_TYPES["강아지"])
        stage_idx = get_stage_index(level)
        emoji = emoji_list[stage_idx]
        rows.append({"닉네임": nickname, "캐릭터": character, "이모지": emoji, "레벨": level, "XP": xp})

    rows.sort(key=lambda r: r["XP"], reverse=True)
    return rows[:top_n]

def get_pet_xp(nickname):
    if not nickname:
        return 0
    base_xp = 0
    if os.path.isfile(CSV_FILE):
        df = pd.read_csv(CSV_FILE, encoding="utf-8-sig")
        user_df = df[df["닉네임"] == nickname]
        resist_count = int((user_df["먹음여부"] == False).sum())
        ate_count = int((user_df["먹음여부"] == True).sum())
        base_xp = resist_count * XP_RESIST + ate_count * XP_ATE
    return base_xp + get_bonus_xp_total(nickname)

def get_stage_index(level):
    if level <= 2:
        return 0
    elif level <= 5:
        return 1
    elif level <= 9:
        return 2
    return 3

def equip_item(nickname, item_str):
    if os.path.isfile(EQUIPPED_FILE):
        df = pd.read_csv(EQUIPPED_FILE, encoding="utf-8-sig")
        df = df[df["닉네임"] != nickname]
    else:
        df = pd.DataFrame(columns=["닉네임", "아이템", "장착시각"])

    new_row = pd.DataFrame([{
        "닉네임": nickname,
        "아이템": item_str,
        "장착시각": now_kst().strftime("%Y-%m-%d %H:%M:%S")
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(EQUIPPED_FILE, index=False, encoding="utf-8-sig")

def get_equipped_item(nickname):
    if not os.path.isfile(EQUIPPED_FILE) or not nickname:
        return None
    df = pd.read_csv(EQUIPPED_FILE, encoding="utf-8-sig")
    matched = df[df["닉네임"] == nickname]
    if len(matched) == 0:
        return None
    return matched.iloc[0]["아이템"]

def get_item_rarity(item_str):
    if not item_str:
        return None
    for item_emoji, item_name, rarity in ITEM_POOL + MILESTONE_ITEM_POOL:
        if item_name in item_str:
            return rarity
    return None

def get_active_boost(nickname):
    if not os.path.isfile(EQUIPPED_FILE) or not nickname:
        return 0.0, 0.0, None
    df = pd.read_csv(EQUIPPED_FILE, encoding="utf-8-sig")
    matched = df[df["닉네임"] == nickname]
    if len(matched) == 0 or "장착시각" not in matched.columns:
        return 0.0, 0.0, None

    row = matched.iloc[0]
    item_str = row["아이템"]
    equipped_at_raw = row.get("장착시각")
    if pd.isna(equipped_at_raw):
        return 0.0, 0.0, item_str

    equipped_at = datetime.strptime(str(equipped_at_raw), "%Y-%m-%d %H:%M:%S")
    hours_passed = (now_kst() - equipped_at).total_seconds() / 3600
    hours_left = ITEM_EFFECT_DURATION_HOURS - hours_passed
    if hours_left <= 0:
        return 0.0, 0.0, item_str

    rarity = get_item_rarity(item_str)
    boost_ratio = RARITY_BOOST.get(rarity, 0.0)
    return boost_ratio, round(hours_left, 1), item_str

def log_bonus_xp(nickname, bonus_xp):
    if bonus_xp <= 0:
        return
    if os.path.isfile(BONUS_XP_FILE):
        df = pd.read_csv(BONUS_XP_FILE, encoding="utf-8-sig")
    else:
        df = pd.DataFrame(columns=["닉네임", "날짜시간", "보너스XP"])
    new_row = pd.DataFrame([{
        "닉네임": nickname,
        "날짜시간": now_kst().strftime("%Y-%m-%d %H:%M:%S"),
        "보너스XP": bonus_xp
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(BONUS_XP_FILE, index=False, encoding="utf-8-sig")

def get_bonus_xp_total(nickname):
    if not os.path.isfile(BONUS_XP_FILE) or not nickname:
        return 0
    df = pd.read_csv(BONUS_XP_FILE, encoding="utf-8-sig")
    user_df = df[df["닉네임"] == nickname]
    return int(user_df["보너스XP"].sum())

def get_pet_status(nickname, character_type):
    xp = get_pet_xp(nickname)
    level = xp // LEVEL_XP_PER_LEVEL + 1
    remaining = LEVEL_XP_PER_LEVEL - (xp % LEVEL_XP_PER_LEVEL)
    stage_idx = get_stage_index(level)
    emoji_list = CHARACTER_TYPES.get(character_type, CHARACTER_TYPES["강아지"])
    emoji = emoji_list[stage_idx]
    stage_name = STAGE_NAMES[stage_idx]

    equipped = get_equipped_item(nickname)
    equipped_name = None
    equipped_rarity = None
    if equipped and isinstance(equipped, str):
        for item_emoji, item_name, rarity in ITEM_POOL + MILESTONE_ITEM_POOL:
            if item_name in equipped:
                equipped_name = f"{item_emoji} {item_name}"
                equipped_rarity = rarity
                break

    boost_ratio, hours_left, _ = get_active_boost(nickname)

    return level, xp, remaining, emoji, stage_name, equipped_name, equipped_rarity, boost_ratio, hours_left

def check_attendance(nickname):
    if not nickname:
        return "먼저 로그인해주세요."
    today = now_kst().strftime("%Y-%m-%d")

    if os.path.isfile(ATTENDANCE_FILE):
        df = pd.read_csv(ATTENDANCE_FILE, encoding="utf-8-sig")
        if len(df[(df["닉네임"] == nickname) & (df["날짜"] == today)]) > 0:
            return "오늘은 이미 출석했어요! 내일 또 와주세요 😊"
    else:
        df = pd.DataFrame(columns=["닉네임", "날짜", "아이템"])

    emoji, name, rarity = random.choice(ITEM_POOL)
    new_row = pd.DataFrame([{"닉네임": nickname, "날짜": today, "아이템": f"{emoji} {name}"}])
    new_row.to_csv(ATTENDANCE_FILE, mode="a" if os.path.isfile(ATTENDANCE_FILE) else "w",
                    header=not os.path.isfile(ATTENDANCE_FILE), index=False, encoding="utf-8-sig")
    return f"출석 완료! {emoji} {name}({rarity})을 획득했어요!"

def get_inventory(nickname):
    if not nickname:
        return {}
    all_items = []
    if os.path.isfile(ATTENDANCE_FILE):
        df = pd.read_csv(ATTENDANCE_FILE, encoding="utf-8-sig")
        all_items += df[df["닉네임"] == nickname]["아이템"].tolist()
    if os.path.isfile(MILESTONE_FILE):
        df2 = pd.read_csv(MILESTONE_FILE, encoding="utf-8-sig")
        all_items += df2[df2["닉네임"] == nickname]["아이템"].tolist()
    if not all_items:
        return {}
    return pd.Series(all_items).value_counts().to_dict()

# ---------- AI 분류/코멘트 ----------

def generate_comment(reason_category, food_name, calorie, exercise, minutes, ate, mode):
    tone = "재치있고 위트있게" if mode == "재치" else "담백하고 진지하게, 다정한 격려 위주로"
    action_text = "먹기로 했어요" if ate else "참았어요"

    prompt = f"""
사용자가 '{food_name}'({calorie}kcal)을 {action_text}.
{exercise} 기준 약 {minutes}분에 해당해요.
먹고 싶었던 이유: "{reason_category}"

{tone} 2문장 이내로 코멘트 해줘. 이모지 1~2개 사용.
다른 설명 없이 코멘트만 출력해줘.
"""
    response = call_gemini_with_retry(prompt)

    if response is None:
        return random.choice(FALLBACK_COMMENTS_ATE if ate else FALLBACK_COMMENTS_RESIST)

    return response.text.strip()

def generate_weight_progress_message(current_weight, goal_weight, ate):
    diff = round(current_weight - goal_weight, 1)

    if diff <= 0:
        return "🎉 목표 체중을 이미 달성하셨어요! 정말 대단해요!", 0.0

    tone = "따끔하게 자극이 되도록" if ate else "진심으로 응원하듯 따뜻하게"
    action_text = "방금 유혹에 넘어가 먹었어요" if ate else "방금 유혹을 참아냈어요"

    prompt = f"""
사용자는 목표 체중까지 {diff}kg이 남았어요. {action_text}.

{tone} 2문장 이내로 코멘트 해줘. 남은 kg 수치를 자연스럽게 언급해줘. 이모지 1개 사용.
다른 설명 없이 코멘트만 출력해줘.
"""
    response = call_gemini_with_retry(prompt)

    if response is None:
        if ate:
            fallback = f"목표까지 아직 {diff}kg 남았어요. 이 선택이 그 거리를 더 멀게 만들 수도 있어요 😬"
        else:
            fallback = f"목표까지 {diff}kg 남았어요! 오늘의 선택이 그 거리를 좁혀줬어요 💪"
        return fallback, diff

    return response.text.strip(), diff

# ---------- 기록 조회 ----------

def get_monthly_calendar(nickname):
    if not nickname or not os.path.isfile(CSV_FILE):
        return {}
    df = pd.read_csv(CSV_FILE, encoding="utf-8-sig")
    df = df[df["닉네임"] == nickname]
    if len(df) == 0:
        return {}
    df["날짜시간"] = pd.to_datetime(df["날짜시간"])
    now = now_kst()
    month_df = df[(df["날짜시간"].dt.year == now.year) & (df["날짜시간"].dt.month == now.month)]

    calendar_data = {}
    for day, group in month_df.groupby(month_df["날짜시간"].dt.day):
        resist = int((group["먹음여부"] == False).sum())
        ate = int((group["먹음여부"] == True).sum())
        calendar_data[int(day)] = {"참음": resist, "먹음": ate}
    return calendar_data

def get_period_records(period, nickname):
    if not nickname:
        return pd.DataFrame(), "먼저 로그인해주세요."
    if not os.path.isfile(CSV_FILE):
        return pd.DataFrame(), "아직 기록이 없어요."

    df = pd.read_csv(CSV_FILE, encoding="utf-8-sig")
    df = df[df["닉네임"] == nickname]
    df["날짜시간"] = pd.to_datetime(df["날짜시간"])
    now = now_kst()

    if period == "이번 주":
        start = now - pd.Timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    filtered = df[df["날짜시간"] >= start].sort_values("날짜시간", ascending=False)

    if len(filtered) == 0:
        return pd.DataFrame(), f"{period} 기록이 아직 없어요."

    ate_count = int(filtered["먹음여부"].sum())
    resist_count = len(filtered) - ate_count
    max_streak = int(filtered["스트릭"].max())
    top_food = filtered["음식명"].value_counts().idxmax()
    top_reason = filtered["이유카테고리"].value_counts().idxmax()

    stats = {
        "총 기록": len(filtered),
        "참음": resist_count,
        "먹음": ate_count,
        "최장 스트릭": max_streak,
        "자주 마주친 음식": top_food,
        "가장 많은 유혹 이유": top_reason,
    }
    display_df = filtered[["날짜시간", "음식명", "칼로리", "먹음여부", "이유카테고리", "환산운동", "필요시간(분)"]]
    return display_df, stats
