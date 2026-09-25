import streamlit as st
import pandas as pd
import os
import re
import time
import zipfile
from io import BytesIO
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

def extract_amount_from_receipt(image_file, target_phone):
    """يحاول يستخرج المبلغ المدفوع من نص الإيصال (تقديري، للمراجعة اليدوية)"""
    try:
        image_file.seek(0)
        image = Image.open(image_file)
        raw_text = pytesseract.image_to_string(image, lang="eng")
        # نشيل رقم التليفون الأول عشان ميتلخبطش مع المبلغ
        text_without_phone = raw_text.replace(target_phone, " ")
        # ندور على أرقام قريبة من كلمة جنيه/EGP/LE الأول
        currency_pattern = re.findall(r"(\d{1,5}(?:[.,]\d{1,2})?)\s*(?:جنيه|EGP|L\.?E\.?|LE)", text_without_phone, re.IGNORECASE)
        if currency_pattern:
            try:
                return float(currency_pattern[0].replace(",", "."))
            except ValueError:
                pass
        # لو مفيش، ندور على أي أرقام معقولة (1 لحد 4 خانات) ونختار أكبر رقم منطقي
        all_numbers = re.findall(r"\d{1,5}(?:[.,]\d{1,2})?", text_without_phone)
        candidates = []
        for n in all_numbers:
            try:
                val = float(n.replace(",", "."))
                if 1 <= val <= 9999:
                    candidates.append(val)
            except ValueError:
                continue
        if candidates:
            return max(candidates)
        return None
    except Exception:
        return None

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
RECEIPTS_DIR = "receipts"
os.makedirs(RECEIPTS_DIR, exist_ok=True)

PAYMENTS_LOG_FILE = "payments_log.csv"
LOG_COLUMNS = ["الاسم رباعي", "رقم الموبايل", "رقم الكرسي", "المبلغ المدخل يدوياً", "المبلغ المكتشف من الإيصال", "حالة التطابق", "ملف الإيصال"]

def log_payment(name, phone, seat, entered_amount, detected_amount, receipt_filename):
    """يسجل تفاصيل كل عملية دفع في سجل منفصل مع حالة مطابقة المبلغ"""
    if detected_amount is None:
        match_status = "⚠️ لم يتم قراءة المبلغ"
    elif abs(detected_amount - entered_amount) <= 5:  # هامش خطأ بسيط لقراءة OCR
        match_status = "✅ مطابق"
    else:
        match_status = "⚠️ غير مطابق"
    row = pd.DataFrame([[name, phone, seat, entered_amount, detected_amount, match_status, receipt_filename]], columns=LOG_COLUMNS)
    if not os.path.exists(PAYMENTS_LOG_FILE):
        row.to_csv(PAYMENTS_LOG_FILE, index=False)
    else:
        row.to_csv(PAYMENTS_LOG_FILE, mode='a', header=False, index=False)

def sanitize_for_filename(text):
    """يشيل أي رموز ممكن تبوّظ اسم الملف ويستبدل المسافات بشرطة تحت"""
    text = re.sub(r"[^\w\u0600-\u06FF]+", "_", str(text).strip())
    return text.strip("_")

def save_receipt(image_file, seat_num, name, phone):
    """يحفظ صورة الإيصال في مجلد receipts باسم فيه المقعد والاسم والرقم والوقت"""
    try:
        image_file.seek(0)
        image = Image.open(image_file).convert("RGB")
        safe_name = sanitize_for_filename(name)
        safe_phone = sanitize_for_filename(phone)
        filename = f"مقعد{seat_num}_{safe_phone}_{safe_name}_{int(time.time())}.jpg"
        filepath = os.path.join(RECEIPTS_DIR, filename)
        image.save(filepath, "JPEG")
        return filepath
    except Exception:
        return None

# التأكد من وجود ملف البيانات أو إنشائه
if not os.path.exists(DB_FILE):
    df_init = pd.DataFrame(columns=COLUMNS)
    df_init.to_csv(DB_FILE, index=False)

# تحميل البيانات الحالية (رقم الموبايل لازم يتقرا كنص عشان الصفر الأول ميتشلش)
df_bookings = pd.read_csv(DB_FILE, dtype={"رقم الموبايل": str})

# لو الملف قديم ومفيهوش عمود المبلغ المدفوع، نضيفه (ترحيل تلقائي)
if "المبلغ المدفوع" not in df_bookings.columns:
    df_bookings["المبلغ المدفوع"] = MIN_DEPOSIT  # نفترض إنهم دفعوا العربون على الأقل
    df_bookings.to_csv(DB_FILE, index=False)

# ترحيل تلقائي: لو رقم موبايل قديم فقد الصفر الأول (10 أرقام بدل 11)، نضيفه تاني
def _fix_missing_zero(p):
    digits = normalize_digits(str(p))
    if len(digits) == 10 and digits[0] != "0":
        return "0" + digits
    return digits

fixed_phones = df_bookings["رقم الموبايل"].apply(_fix_missing_zero)
if not fixed_phones.equals(df_bookings["رقم الموبايل"].astype(str)):
    df_bookings["رقم الموبايل"] = fixed_phones
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
    elif is_valid_name(name) and name.strip() in df_bookings["الاسم رباعي"].astype(str).str.strip().values:
        st.error("أنت مسجل مسبقاً ولديك حجز قائم. برجاء التوجه لقسم 'استكمال دفع حجز' تحت لإكمال الدفع.")
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
        receipt_path = save_receipt(uploaded_file, selected_seat, name, phone)  # حفظ صورة الإيصال
        receipt_filename = os.path.basename(receipt_path) if receipt_path else ""
        detected_amount = extract_amount_from_receipt(uploaded_file, TARGET_PHONE)
        log_payment(name, phone, selected_seat, amount_paid, detected_amount, receipt_filename)
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
    complete_phone = st.text_input("أدخل رقم الموبايل اللي حجزت بيه", key="complete_phone")

    if complete_phone:
        digits_input = normalize_digits(complete_phone)
        df_bookings["_رقم_منظم"] = df_bookings["رقم الموبايل"].astype(str).apply(normalize_digits)
        matches = df_bookings[df_bookings["_رقم_منظم"] == digits_input]

        if len(matches) == 0:
            st.error("لم يتم العثور على أي حجز بهذا الرقم. تأكد من كتابة الرقم بشكل صحيح.")
        else:
            # لو نفس الرقم حجز أكتر من مقعد، نخليه يختار أنهي واحد
            if len(matches) > 1:
                options_labels = [
                    f"مقعد {row['رقم الكرسي']} - {row['الاسم رباعي']}"
                    for _, row in matches.iterrows()
                ]
                chosen_label = st.selectbox("عندك أكتر من حجز بنفس الرقم، اختار الحجز اللي عايز تكمله", options=options_labels, key="choose_booking")
                chosen_idx = options_labels.index(chosen_label)
                row_idx = [matches.index[chosen_idx]]
            else:
                row_idx = [matches.index[0]]

            current_paid = df_bookings.loc[row_idx[0], "المبلغ المدفوع"]
            complete_seat = df_bookings.loc[row_idx[0], "رقم الكرسي"]
            complete_name = df_bookings.loc[row_idx[0], "الاسم رباعي"]
            remaining_now = TOTAL_PRICE - current_paid

            if remaining_now <= 0:
                st.success(f"المقعد رقم {complete_seat} مسدد بالكامل ✅ ({current_paid} من {TOTAL_PRICE} جنيه).")
            else:
                st.info(f"مقعد رقم {complete_seat} — المدفوع حتى الآن: {current_paid} جنيه من أصل {TOTAL_PRICE} جنيه — المتبقي: **{remaining_now} جنيه**")
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
                        df_bookings.drop(columns=["_رقم_منظم"]).to_csv(DB_FILE, index=False)
                        receipt_path = save_receipt(new_receipt, complete_seat, complete_name, complete_phone)  # حفظ صورة إيصال الدفعة
                        receipt_filename = os.path.basename(receipt_path) if receipt_path else ""
                        detected_amount = extract_amount_from_receipt(new_receipt, TARGET_PHONE)
                        log_payment(complete_name, complete_phone, complete_seat, new_payment, detected_amount, receipt_filename)
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
        df_all = pd.read_csv(DB_FILE, dtype={"رقم الموبايل": str})
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

        st.markdown("---")
        st.subheader("🗑️ حذف حجز")

        if len(df_all) > 0:
            delete_labels = [
                f"مقعد {row['رقم الكرسي']} - {row['الاسم رباعي']} - {row['رقم الموبايل']}"
                for _, row in df_all.iterrows()
            ]
            delete_choice = st.selectbox("اختر الحجز اللي عايز تحذفه", options=delete_labels, key="admin_delete_choice")
            delete_idx = delete_labels.index(delete_choice)

            confirm_delete = st.checkbox("متأكد إني عايز أحذف الحجز ده نهائياً", key="confirm_delete")
            if st.button("🗑️ حذف الحجز دلوقتي", type="primary"):
                if not confirm_delete:
                    st.error("برجاء تحديد مربع التأكيد فوق الأول.")
                else:
                    df_after_delete = df_all.drop(columns=["المتبقي"]).drop(index=df_all.index[delete_idx])
                    df_after_delete.to_csv(DB_FILE, index=False)
                    st.success("تم حذف الحجز بنجاح. المقعد بقى متاح تاني.")
                    st.rerun()
        else:
            st.info("مفيش حجوزات عشان تتحذف.")

        st.markdown("---")
        st.subheader("🧾 سجل الدفعات ومطابقة المبالغ")

        if os.path.exists(PAYMENTS_LOG_FILE):
            df_log = pd.read_csv(PAYMENTS_LOG_FILE, dtype={"رقم الموبايل": str})
            st.dataframe(df_log, use_container_width=True)

            st.markdown("**عرض إيصال معيّن:**")
            log_labels = [
                f"{i+1}) مقعد {row['رقم الكرسي']} - {row['الاسم رباعي']} - {row['حالة التطابق']}"
                for i, row in df_log.iterrows()
            ]
            chosen = st.selectbox("اختر الدفعة اللي عايز تشوف إيصالها", options=log_labels, key="admin_choose_receipt")
            chosen_idx = log_labels.index(chosen)
            chosen_filename = df_log.iloc[chosen_idx]["ملف الإيصال"]
            chosen_filepath = os.path.join(RECEIPTS_DIR, str(chosen_filename))
            if chosen_filename and os.path.exists(chosen_filepath):
                st.image(chosen_filepath, caption=str(chosen_filename), width=350)
            else:
                st.warning("صورة الإيصال دي مش موجودة (ممكن تكون اتمسحت مع إعادة تشغيل السيرفر).")

            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                if os.path.exists(PAYMENTS_LOG_FILE):
                    zf.write(PAYMENTS_LOG_FILE, arcname="payments_log.csv")
                if os.path.exists(RECEIPTS_DIR):
                    for fname in os.listdir(RECEIPTS_DIR):
                        zf.write(os.path.join(RECEIPTS_DIR, fname), arcname=f"receipts/{fname}")
            st.download_button(
                label="⬇️ تنزيل سجل الدفعات + كل الإيصالات (ZIP)",
                data=zip_buffer.getvalue(),
                file_name="payments_and_receipts.zip",
                mime="application/zip"
            )
        else:
            st.info("لا يوجد سجل دفعات بعد.")
    elif admin_pass_input != "":
        st.error("كلمة السر غير صحيحة.")