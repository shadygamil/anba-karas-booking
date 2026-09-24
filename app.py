import streamlit as st
import pandas as pd
import os
import re
from PIL import Image
import pytesseract

# رقم الموبايل اللي هيستلم عليه التحويلات (إنستا باي / فودافون كاش)
TARGET_PHONE = "01225427767"

# أسعار الرحلة
TOTAL_PRICE = 250   # السعر الكامل للرحلة
MIN_DEPOSIT = 125   # أقل مبلغ لازم يتدفع عشان يثبت الحجز (عربون)

def normalize_digits(text):
    """يحول أي أرقام عربية لإنجليزية ويشيل أي حاجة مش رقم"""
    arabic_to_english = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    text = text.translate(arabic_to_english)
    return re.sub(r"\D", "", text)

def check_receipt_for_phone(image_file, target_phone):
    """يحاول يقرا الرقم من صورة الإيصال ويتأكد إنه موجود فيها"""
    try:
        image = Image.open(image_file)
        raw_text = pytesseract.image_to_string(image, lang="eng")
        digits_only = normalize_digits(raw_text)
        return target_phone in digits_only
    except Exception:
        return False

def is_valid_name(name):
    """لازم يكون اسم رباعي: أربع كلمات على الأقل، حروف بس (عربي أو إنجليزي)"""
    parts = name.strip().split()
    if len(parts) < 4:
        return False
    for part in parts:
        if not re.fullmatch(r"[A-Za-z\u0600-\u06FF]+", part):
            return False
    return True

def is_valid_phone(phone):
    """رقم موبايل مصري صحيح: 11 رقم ويبدأ بـ 010 أو 011 أو 012 أو 015"""
    digits = normalize_digits(phone)
    return bool(re.fullmatch(r"01[0125]\d{8}", digits))

# إعدادات الصفحة
st.set_page_config(page_title="حجز مقاعد أسرة الأنبا كراس", page_icon="🚌", layout="centered")

st.title("🚌 حجز رحلة أسرة الأنبا كراس")
st.markdown("---")

DB_FILE = "bookings.csv"
COLUMNS = ["الاسم رباعي", "رقم الموبايل", "رقم الكرسي", "المبلغ المدفوع"]

# التأكد من وجود ملف البيانات أو إنشائه
if not os.path.exists(DB_FILE):
    df_init = pd.DataFrame(columns=COLUMNS)
    df_init.to_csv(DB_FILE, index=False)

# تحميل البيانات الحالية
df_bookings = pd.read_csv(DB_FILE)

# لو الملف قديم ومفيهوش عمود المبلغ المدفوع، نضيفه (ترحيل تلقائي)
if "المبلغ المدفوع" not in df_bookings.columns:
    df_bookings["المبلغ المدفوع"] = MIN_DEPOSIT  # نفترض إنهم دفعوا العربون على الأقل
    df_bookings.to_csv(DB_FILE, index=False)

booked_seats = df_bookings["رقم الكرسي"].tolist()

# تهيئة حالة الجلسة (لازم قبل أي استخدام ليها)
if 'selected_seat' not in st.session_state:
    st.session_state['selected_seat'] = None
if 'form_counter' not in st.session_state:
    st.session_state['form_counter'] = 0

# إدخال بيانات المستخدم
st.subheader("📝 بيانات الحجز")
name = st.text_input("الاسم رباعي", key=f"name_{st.session_state['form_counter']}")
phone = st.text_input("رقم الموبايل", key=f"phone_{st.session_state['form_counter']}")

st.markdown("---")

# خريطة مقاعد الأتوبيس الاحترافية تماماً مثل تطبيقات الحجز
st.subheader("🚌 خريطة مقاعد الأتوبيس")
st.markdown("---")

# مقدمة الأتوبيس (السائق والباب)
col_f1, col_f2, col_f3 = st.columns([2, 2, 2])
with col_f1:
    st.markdown("🧑‍✈️ **[ السائق ]**")
with col_f3:
    st.info("🚪 باب الأتوبيس")

st.markdown("---")
st.info("🟢 مقعد متاح  |  🔴 مقعد محجوز")

total_seats = 49  # إجمالي عدد مقاعد الأتوبيس

# الصفوف العادية (من 1 إلى 44: كل صف 4 كراسي: كرسيين، ممر في النص، كرسيين)
for row in range(0, 44, 4):
    c1, c2, spacer, c3, c4 = st.columns([2, 2, 1, 2, 2])
    row_seats = [row + 1, row + 2, row + 3, row + 4]
    col_list = [c1, c2, c3, c4]
    
    for idx, seat_num in enumerate(row_seats):
        if seat_num <= total_seats:
            is_booked = seat_num in booked_seats
            btn_label = f"🔴 {seat_num}" if is_booked else f"🟢 {seat_num}"
            with col_list[idx]:
                if is_booked:
                    st.button(btn_label, disabled=True, key=f"seat_{seat_num}")
                else:
                    if st.button(btn_label, key=f"seat_{seat_num}"):
                        st.session_state['selected_seat'] = seat_num
                        st.success(f"تم اختيار المقعد: {seat_num}")

# الصف الأخير (من 45 إلى 49: 5 كراسي جنب بعض تماماً مثل الصورة)
st.write("---") 
last_row_cols = st.columns(5)
last_row_seats = [45, 46, 47, 48, 49]

for idx, seat_num in enumerate(last_row_seats):
    is_booked = seat_num in booked_seats
    btn_label = f"🔴 {seat_num}" if is_booked else f"🟢 {seat_num}"
    with last_row_cols[idx]:
        if is_booked:
            st.button(btn_label, disabled=True, key=f"seat_{seat_num}")
        else:
            if st.button(btn_label, key=f"seat_{seat_num}"):
                st.session_state['selected_seat'] = seat_num
                st.success(f"تم اختيار المقعد: {seat_num}")

st.markdown("---")
selected_seat = st.session_state.get('selected_seat')
if selected_seat:
    st.write(f"✅ المقعد المحدد حالياً للحجز: **{selected_seat}**")
else:
    st.warning("⚠️ برجاء اختيار مقعد من خريطة الأتوبيس بالأعلى.")

st.markdown("---")
st.info(f"💳 حوّل المبلغ على الرقم: **{TARGET_PHONE}** (إنستا باي أو فودافون كاش). سعر الرحلة الكامل {TOTAL_PRICE} جنيه، وأقل مبلغ لتثبيت الحجز {MIN_DEPOSIT} جنيه.")
amount_paid = st.number_input("المبلغ اللي دفعته في هذا التحويل (جنيه)", min_value=0, step=5, key=f"amount_{st.session_state['form_counter']}")
uploaded_file = st.file_uploader(
    "رفع صورة إيصال التحويل (فودافون كاش / إنستا باي)",
    type=["png", "jpg", "jpeg"],
    key=f"uploader_{st.session_state['form_counter']}"
)

receipt_verified = False

if uploaded_file is not None:
    with st.spinner("جاري التحقق من الإيصال..."):
        receipt_verified = check_receipt_for_phone(uploaded_file, TARGET_PHONE)
    uploaded_file.seek(0)  # نرجع مؤشر الملف لأول حاجة عشان نقدر نستخدمه تاني

    if receipt_verified:
        st.success(f"✅ تم التحقق: الرقم {TARGET_PHONE} ظاهر في الإيصال.")
    else:
        st.error("❌ لم يتم العثور على الرقم بوضوح في الصورة. برجاء التأكد إن الصورة واضحة وغير مشخبط عليها، وصوّرها تاني وارفعها من جديد.")

st.markdown("---")

if st.button("تأكيد الحجز"):
    if not name or not phone:
        st.error("برجاء إدخال الاسم ورقم الموبايل.")
    elif not is_valid_name(name):
        st.error("برجاء إدخال اسم رباعي كامل (أربع كلمات على الأقل، حروف فقط).")
    elif not is_valid_phone(phone):
        st.error("برجاء إدخال رقم موبايل مصري صحيح (11 رقم يبدأ بـ 010 أو 011 أو 012 أو 015).")
    elif selected_seat is None:
        st.error("برجاء اختيار مقعد من الأتوبيس أولاً.")
    elif amount_paid < MIN_DEPOSIT:
        st.error(f"أقل مبلغ لتثبيت الحجز هو {MIN_DEPOSIT} جنيه. برجاء إدخال المبلغ الصحيح.")
    elif uploaded_file is None:
        st.error("برجاء رفع صورة إيصال التحويل.")
    elif not receipt_verified:
        st.error("لم يتم التحقق من الإيصال. برجاء رفع صورة أوضح تظهر فيها رقم التحويل بشكل جيد.")
    else:
        # حفظ الحجز الجديد
        new_data = pd.DataFrame([[name, phone, selected_seat, amount_paid]], columns=COLUMNS)
        new_data.to_csv(DB_FILE, mode='a', header=False, index=False)
        remaining = TOTAL_PRICE - amount_paid
        if remaining > 0:
            st.success(f"تم حجز المقعد رقم {selected_seat} بنجاح! باقي عليك {remaining} جنيه، تقدر تكملها من قسم 'استكمال دفع حجز' تحت.")
        else:
            st.success(f"تم حجز المقعد رقم {selected_seat} بنجاح! تم سداد المبلغ بالكامل. مبروك.")
        st.session_state['selected_seat'] = None
        st.session_state['form_counter'] += 1  # يصفّر الاسم والرقم والإيصال المرفوع
        st.rerun()

# ==================== استكمال دفع حجز موجود ====================
st.markdown("---")
st.subheader("💰 استكمال دفع حجز موجود")

if len(booked_seats) > 0:
    complete_seat = st.selectbox("اختر رقم الكرسي اللي حجزته", options=sorted(booked_seats), key="complete_seat")
    row_idx = df_bookings[df_bookings["رقم الكرسي"] == complete_seat].index
    if len(row_idx) > 0:
        current_paid = df_bookings.loc[row_idx[0], "المبلغ المدفوع"]
        remaining_now = TOTAL_PRICE - current_paid
        if remaining_now <= 0:
            st.success(f"المقعد رقم {complete_seat} مسدد بالكامل ✅ ({current_paid} من {TOTAL_PRICE} جنيه).")
        else:
            st.info(f"المدفوع حتى الآن: {current_paid} جنيه من أصل {TOTAL_PRICE} جنيه — المتبقي: **{remaining_now} جنيه**")
            new_payment = st.number_input("المبلغ اللي هتدفعه دلوقتي (جنيه)", min_value=0, max_value=int(remaining_now), step=5, key="new_payment_amount")
            new_receipt = st.file_uploader("ارفع صورة إيصال الدفعة الجديدة", type=["png", "jpg", "jpeg"], key="new_payment_receipt")

            new_receipt_verified = False
            if new_receipt is not None:
                with st.spinner("جاري التحقق من الإيصال..."):
                    new_receipt_verified = check_receipt_for_phone(new_receipt, TARGET_PHONE)
                if new_receipt_verified:
                    st.success(f"✅ تم التحقق: الرقم {TARGET_PHONE} ظاهر في الإيصال.")
                else:
                    st.error("❌ لم يتم العثور على الرقم بوضوح في الصورة. صوّرها تاني وارفعها من جديد.")

            if st.button("تسجيل الدفعة"):
                if new_payment <= 0:
                    st.error("برجاء إدخال مبلغ أكبر من صفر.")
                elif new_receipt is None:
                    st.error("برجاء رفع صورة إيصال الدفعة.")
                elif not new_receipt_verified:
                    st.error("لم يتم التحقق من الإيصال. برجاء رفع صورة أوضح.")
                else:
                    df_bookings.loc[row_idx[0], "المبلغ المدفوع"] = current_paid + new_payment
                    df_bookings.to_csv(DB_FILE, index=False)
                    new_remaining = TOTAL_PRICE - (current_paid + new_payment)
                    if new_remaining <= 0:
                        st.success("تم تسجيل الدفعة! تم سداد المبلغ بالكامل 🎉")
                    else:
                        st.success(f"تم تسجيل الدفعة! المتبقي الآن: {new_remaining} جنيه")
                    st.rerun()
else:
    st.info("مفيش حجوزات لسه.")

# ==================== صفحة الإدارة ====================
ADMIN_PASSWORD = "anbakaras"

st.markdown("---")
with st.expander("🔐 لوحة الإدارة (للمسؤول فقط)"):
    admin_pass_input = st.text_input("كلمة السر", type="password", key="admin_pass")
    if admin_pass_input == ADMIN_PASSWORD:
        st.success("تم الدخول بنجاح ✅")
        df_all = pd.read_csv(DB_FILE)
        df_all["المتبقي"] = TOTAL_PRICE - df_all["المبلغ المدفوع"]

        st.subheader(f"📋 كل الحجوزات ({len(df_all)} حجز)")
        st.dataframe(df_all, use_container_width=True)

        total_collected = df_all["المبلغ المدفوع"].sum()
        st.metric("💰 إجمالي المبلغ المحصّل", f"{total_collected} جنيه")

        csv_data = df_all.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="⬇️ تنزيل ملف الحجوزات (Excel/CSV)",
            data=csv_data,
            file_name="bookings_export.csv",
            mime="text/csv"
        )
    elif admin_pass_input != "":
        st.error("كلمة السر غير صحيحة.")