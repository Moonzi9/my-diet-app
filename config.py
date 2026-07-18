import os
import unicodedata
import pandas as pd
import google.generativeai as genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-flash-latest")

CSV_FILE = "temptation_log.csv"
PROFILE_FILE = "user_profiles.csv"
ATTENDANCE_FILE = "attendance_log.csv"
EQUIPPED_FILE = "equipped_item.csv"
MILESTONE_FILE = "milestone_log.csv"
MILESTONE_THRESHOLDS = [3, 5, 10]

BONUS_XP_FILE = "bonus_xp_log.csv"
ITEM_EFFECT_DURATION_HOURS = 24


def find_file(keyword, ext):
    keyword_norm = unicodedata.normalize("NFC", keyword)
    for f in os.listdir():
        f_norm = unicodedata.normalize("NFC", f)
        if f_norm.endswith(ext) and keyword_norm in f_norm:
            return f
    return None


FOOD_DATA_FILE = find_file("음식", ".csv")
EXTRA_FOOD_FILE = find_file("가공식품", ".xlsx")

print("음식 CSV:", FOOD_DATA_FILE)
print("가공식품 엑셀:", EXTRA_FOOD_FILE)

if FOOD_DATA_FILE is None:
    raise FileNotFoundError(
        "⚠️ '음식'이 포함된 .csv 파일을 찾을 수 없어요. "
        "전국통합식품영양성분정보_음식_표준데이터.csv 파일을 이 세션에 업로드한 뒤 다시 실행해주세요."
    )

food_df = pd.read_csv(FOOD_DATA_FILE, encoding="cp949")

if EXTRA_FOOD_FILE:
    extra_raw = pd.read_excel(EXTRA_FOOD_FILE, sheet_name=0)
    extra_raw.columns = [c.replace("\n", "") if isinstance(c, str) else c for c in extra_raw.columns]
    extra_raw = extra_raw.rename(columns={
        "가공식품품목명": "식품명",
        "영양성분기준용량": "영양성분함량기준량",
    })

    keep_cols = ["식품명", "대표식품명", "영양성분함량기준량", "에너지(kcal)", "탄수화물(g)", "단백질(g)", "지방(g)"]
    extra_small = extra_raw[keep_cols].copy()

    for col in food_df.columns:
        if col not in extra_small.columns:
            extra_small[col] = None
    extra_small = extra_small[food_df.columns]

    food_df = pd.concat([food_df, extra_small], ignore_index=True)

MET_TABLE = {
    "헬스(가벼운 강도)": 3.0,
    "헬스(고강도/보디빌딩)": 6.0,
    "헬스(서킷트레이닝)": 8.0,
    "필라테스": 3.0,
    "발레": 4.8,
    "요가": 2.5,
    "러닝": 9.8,
    "걷기": 3.5,
    "줄넘기": 11.0,
    "계단오르기": 8.8,
    "수영": 7.0,
    "자전거": 7.5,
}

EXERCISE_EMOJIS = {
    "헬스(가벼운 강도)": "🏋️",
    "헬스(고강도/보디빌딩)": "🏋️‍♂️",
    "헬스(서킷트레이닝)": "🔥",
    "필라테스": "🧘‍♀️",
    "발레": "🩰",
    "요가": "🧘",
    "러닝": "🏃",
    "걷기": "🚶",
    "줄넘기": "🪢",
    "계단오르기": "🪜",
    "수영": "🏊",
    "자전거": "🚴",
}

EXERCISE_VIDEOS = {
    "헬스(가벼운 강도)": "https://www.youtube.com/watch?v=rBMgABLzXUQ",
    "헬스(고강도/보디빌딩)": "https://www.youtube.com/watch?v=rBMgABLzXUQ",
    "헬스(서킷트레이닝)": "https://www.youtube.com/watch?v=rBMgABLzXUQ",
    "필라테스": "https://www.youtube.com/watch?v=WVPZ-biUoDo",
    "발레": "https://www.youtube.com/watch?v=WVPZ-biUoDo",
    "요가": "https://www.youtube.com/watch?v=HJCAn9WjxJU",
    "러닝": "https://www.youtube.com/watch?v=pUq1JIQFMwE",
    "걷기": "https://www.youtube.com/watch?v=pUq1JIQFMwE",
    "줄넘기": "https://www.youtube.com/watch?v=n1BChV4Nzwg",
    "계단오르기": "https://www.youtube.com/watch?v=pUq1JIQFMwE",
    "수영": "https://www.youtube.com/watch?v=pUq1JIQFMwE",
    "자전거": "https://www.youtube.com/watch?v=vOcwwdsme34",
}

XP_RESIST = 10
XP_ATE = 2
LEVEL_XP_PER_LEVEL = 20

SECURITY_QUESTIONS = [
    "최애 음식은?",
    "가장 좋아하는 운동은?",
    "어릴 때 별명은?",
]

CHARACTER_TYPES = {
    "강아지": ["🐶", "🐕", "🐕‍🦺", "🦮"],
    "고양이": ["🐱", "🐈", "😼", "🦁"],
    "용": ["🥚", "🐣", "🐲", "🐉"],
    "공룡": ["🥚", "🦎", "🦖", "🦕"],
}

STAGE_NAMES = ["새싹 단계", "성장 중", "훈련 완료", "레전드"]

CONDITION_OPTIONS = [
    ("🤩", "최고"),
    ("😊", "개운함"),
    ("😐", "보통"),
    ("😩", "지침"),
    ("😫", "힘듦"),
    ("🤒", "컨디션 나쁨"),
]

REASON_CATEGORIES = ["스트레스", "배고픔", "심심함", "습관", "사회적 상황(약속/모임)"]

ITEM_POOL = [
    ("🎀", "리본", "일반"),
    ("👑", "왕관", "희귀"),
    ("🍀", "네잎클로버", "희귀"),
    ("⭐", "별", "일반"),
    ("🎈", "풍선", "일반"),
    ("🌸", "꽃", "일반"),
    ("💎", "보석", "희귀"),
    ("🧢", "모자", "일반"),
]

MILESTONE_ITEM_POOL = [
    ("🔥", "불꽃 훈장", "레전드"),
    ("💪", "의지의 팔찌", "레전드"),
    ("🌟", "노력의 별", "레전드"),
    ("🏅", "인내의 메달", "레전드"),
]

RARITY_BOOST = {"일반": 0.05, "희귀": 0.15, "레전드": 0.30}

FALLBACK_COMMENTS_RESIST = [
    "오늘도 잘 참으셨어요! 스스로를 칭찬해주세요 🎉",
    "이 순간을 넘긴 게 벌써 대단한 거예요 💪",
    "참을성 레벨업! 오늘의 승자는 당신입니다 🏆",
]
FALLBACK_COMMENTS_ATE = [
    "괜찮아요, 다음 끼니에서 균형 맞추면 돼요 😊",
    "가끔은 맛있게 먹는 것도 필요해요, 내일 다시 힘내봐요 🍽️",
]
