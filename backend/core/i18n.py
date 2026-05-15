"""Multilingual message templates for WhatsApp + Email notifications.

Supported languages (BCP-47-ish 2-letter codes):
    en — English
    hi — Hindi
    ta — Tamil
    te — Telugu
    kn — Kannada
    mr — Marathi
    bn — Bengali
    gu — Gujarati

Each template is a string with {placeholder} format. Call `render(name, lang, **kwargs)`.
Falls back to English when a language is missing or a key is absent.

Templates intentionally avoid heavy emoji to keep WhatsApp + SMS character cost low.
"""
from typing import Any

SUPPORTED_LANGUAGES = ["en", "hi", "ta", "te", "kn", "mr", "bn", "gu"]

LANGUAGE_LABELS = {
    "en": "English",
    "hi": "हिन्दी (Hindi)",
    "ta": "தமிழ் (Tamil)",
    "te": "తెలుగు (Telugu)",
    "kn": "ಕನ್ನಡ (Kannada)",
    "mr": "मराठी (Marathi)",
    "bn": "বাংলা (Bengali)",
    "gu": "ગુજરાતી (Gujarati)",
}

# Template structure: TEMPLATES[name][lang] = "format string with {placeholders}"
TEMPLATES: dict[str, dict[str, str]] = {
    # ---------- Attendance absent ----------
    "attendance_absent": {
        "en": "{school_name}: {student_name} ({student_uid}) was marked ABSENT on {date}. Please reply if this is incorrect.",
        "hi": "{school_name}: {date} को {student_name} ({student_uid}) अनुपस्थित दर्ज किया गया। यदि यह गलत है तो उत्तर दें।",
        "ta": "{school_name}: {date} அன்று {student_name} ({student_uid}) வராதவராக குறிக்கப்பட்டார். தவறு என்றால் பதிலளிக்கவும்.",
        "te": "{school_name}: {date} న {student_name} ({student_uid}) హాజరు కాలేదు అని గుర్తించబడింది. తప్పు అయితే ప్రత్యుత్తరం ఇవ్వండి.",
        "kn": "{school_name}: {date} ರಂದು {student_name} ({student_uid}) ಗೈರು ಎಂದು ಗುರುತಿಸಲಾಗಿದೆ. ತಪ್ಪಾಗಿದ್ದರೆ ಪ್ರತಿಕ್ರಿಯಿಸಿ.",
        "mr": "{school_name}: {date} रोजी {student_name} ({student_uid}) अनुपस्थित नोंदविले आहे. चुकीचे असल्यास उत्तर द्या.",
        "bn": "{school_name}: {date} তারিখে {student_name} ({student_uid}) অনুপস্থিত হিসাবে চিহ্নিত হয়েছে। ভুল হলে উত্তর দিন।",
        "gu": "{school_name}: {date} ના રોજ {student_name} ({student_uid}) ગેરહાજર નોંધવામાં આવ્યા છે. ખોટું હોય તો જવાબ આપો.",
    },
    # ---------- Marks published ----------
    "marks_published": {
        "en": "{school_name}: Marks for {exam_name} are now available. View them on the parent portal.",
        "hi": "{school_name}: {exam_name} के अंक अब उपलब्ध हैं। पैरेंट पोर्टल पर देखें।",
        "ta": "{school_name}: {exam_name} மதிப்பெண்கள் வெளியிடப்பட்டுள்ளன. பெற்றோர் போர்ட்டலில் காண்க.",
        "te": "{school_name}: {exam_name} మార్కులు ఇప్పుడు అందుబాటులో ఉన్నాయి. పేరెంట్ పోర్టల్‌లో చూడండి.",
        "kn": "{school_name}: {exam_name} ಅಂಕಗಳು ಲಭ್ಯವಿವೆ. ಪೋಷಕರ ಪೋರ್ಟಲ್‌ನಲ್ಲಿ ನೋಡಿ.",
        "mr": "{school_name}: {exam_name} गुण उपलब्ध आहेत. पालक पोर्टलवर पहा.",
        "bn": "{school_name}: {exam_name} এর নম্বর প্রকাশিত হয়েছে। প্যারেন্ট পোর্টালে দেখুন।",
        "gu": "{school_name}: {exam_name} ના ગુણ ઉપલબ્ધ છે. પેરન્ટ પોર્ટલ પર જુઓ.",
    },
    # ---------- Payment confirmed ----------
    "payment_confirmed": {
        "en": "{school_name}: Payment of INR {amount} received for {student_name}. Receipt: {receipt_no}.",
        "hi": "{school_name}: {student_name} के लिए INR {amount} का भुगतान प्राप्त हुआ। रसीद: {receipt_no}.",
        "ta": "{school_name}: {student_name} க்காக INR {amount} கட்டணம் பெறப்பட்டது. ரசீது: {receipt_no}.",
        "te": "{school_name}: {student_name} కోసం INR {amount} చెల్లింపు అందుకున్నాము. రసీదు: {receipt_no}.",
        "kn": "{school_name}: {student_name} ಗಾಗಿ INR {amount} ಪಾವತಿ ಸ್ವೀಕರಿಸಲಾಗಿದೆ. ರಶೀದಿ: {receipt_no}.",
        "mr": "{school_name}: {student_name} साठी INR {amount} पेमेंट प्राप्त झाले. पावती: {receipt_no}.",
        "bn": "{school_name}: {student_name} এর জন্য INR {amount} পেমেন্ট প্রাপ্ত হয়েছে। রসিদ: {receipt_no}.",
        "gu": "{school_name}: {student_name} માટે INR {amount} ચૂકવણી મળી. રસીદ: {receipt_no}.",
    },
    # ---------- Monthly digest ----------
    "monthly_digest": {
        "en": (
            "{school_name} — Monthly update for {student_name} ({student_uid})\n"
            "Period: {period}\n"
            "Attendance: {att_line}\n"
            "Marks: {marks_line}\n"
            "Fees: {fee_line}\n"
            "Reply STOP to opt out."
        ),
        "hi": (
            "{school_name} — {student_name} ({student_uid}) के लिए मासिक अपडेट\n"
            "अवधि: {period}\n"
            "उपस्थिति: {att_line}\n"
            "अंक: {marks_line}\n"
            "शुल्क: {fee_line}\n"
            "रोकने के लिए STOP भेजें।"
        ),
        "ta": (
            "{school_name} — {student_name} ({student_uid}) க்கான மாதாந்திர அறிக்கை\n"
            "காலம்: {period}\n"
            "வருகை: {att_line}\n"
            "மதிப்பெண்கள்: {marks_line}\n"
            "கட்டணம்: {fee_line}\n"
            "நிறுத்த STOP அனுப்பவும்."
        ),
        "te": (
            "{school_name} — {student_name} ({student_uid}) కోసం నెలవారీ నివేదిక\n"
            "కాలం: {period}\n"
            "హాజరు: {att_line}\n"
            "మార్కులు: {marks_line}\n"
            "ఫీజు: {fee_line}\n"
            "ఆపడానికి STOP అని పంపండి."
        ),
        "kn": (
            "{school_name} — {student_name} ({student_uid}) ಗಾಗಿ ಮಾಸಿಕ ವರದಿ\n"
            "ಅವಧಿ: {period}\n"
            "ಹಾಜರಾತಿ: {att_line}\n"
            "ಅಂಕಗಳು: {marks_line}\n"
            "ಶುಲ್ಕ: {fee_line}\n"
            "ನಿಲ್ಲಿಸಲು STOP ಕಳುಹಿಸಿ."
        ),
        "mr": (
            "{school_name} — {student_name} ({student_uid}) साठी मासिक अहवाल\n"
            "कालावधी: {period}\n"
            "उपस्थिती: {att_line}\n"
            "गुण: {marks_line}\n"
            "शुल्क: {fee_line}\n"
            "थांबवण्यासाठी STOP पाठवा."
        ),
        "bn": (
            "{school_name} — {student_name} ({student_uid}) এর মাসিক আপডেট\n"
            "সময়: {period}\n"
            "উপস্থিতি: {att_line}\n"
            "নম্বর: {marks_line}\n"
            "ফি: {fee_line}\n"
            "বন্ধ করতে STOP পাঠান।"
        ),
        "gu": (
            "{school_name} — {student_name} ({student_uid}) માટે માસિક અહેવાલ\n"
            "સમયગાળો: {period}\n"
            "હાજરી: {att_line}\n"
            "ગુણ: {marks_line}\n"
            "ફી: {fee_line}\n"
            "બંધ કરવા STOP મોકલો."
        ),
    },
    # ---------- Subscription renewal nudge ----------
    "subscription_renewal": {
        "en": "{school_name}: Your SCMS subscription expires on {valid_until} ({days_left} days). Please renew at {renew_url} to keep all features active.",
        "hi": "{school_name}: आपकी SCMS सदस्यता {valid_until} को समाप्त हो रही है ({days_left} दिन शेष)। सुविधाएँ चालू रखने के लिए {renew_url} पर रिन्यू करें।",
        "ta": "{school_name}: உங்கள் SCMS சந்தா {valid_until} அன்று முடிகிறது ({days_left} நாட்கள் மீதம்). {renew_url} இல் புதுப்பிக்கவும்.",
        "te": "{school_name}: మీ SCMS సబ్‌స్క్రిప్షన్ {valid_until} న ముగుస్తుంది ({days_left} రోజులు మిగిలి). {renew_url} వద్ద పునరుద్ధరించండి.",
        "kn": "{school_name}: ನಿಮ್ಮ SCMS ಚಂದಾದಾರಿಕೆ {valid_until} ರಂದು ಮುಗಿಯುತ್ತದೆ ({days_left} ದಿನ ಬಾಕಿ). {renew_url} ನಲ್ಲಿ ನವೀಕರಿಸಿ.",
        "mr": "{school_name}: तुमची SCMS सदस्यता {valid_until} रोजी संपते ({days_left} दिवस शिल्लक). {renew_url} वर नूतनीकरण करा.",
        "bn": "{school_name}: আপনার SCMS সাবস্ক্রিপশন {valid_until} তারিখে শেষ হবে ({days_left} দিন বাকি)। {renew_url} এ নবায়ন করুন।",
        "gu": "{school_name}: તમારી SCMS સબ્સ્ક્રિપ્શન {valid_until} ના રોજ સમાપ્ત થાય છે ({days_left} દિવસ બાકી). {renew_url} પર નવીકરણ કરો.",
    },
}


def render(name: str, lang: str | None, **kwargs: Any) -> str:
    """Render a template by name + language with kwargs. Falls back to English."""
    family = TEMPLATES.get(name)
    if not family:
        raise KeyError(f"Unknown template: {name}")
    lang = (lang or "en").lower()
    tpl = family.get(lang) or family.get("en")
    if not tpl:
        raise KeyError(f"Template {name} has no English fallback")
    # Safe format: missing keys → empty string, never KeyError.
    class _SafeDict(dict):
        def __missing__(self, key):
            return ""
    return tpl.format_map(_SafeDict(kwargs))


def supported_languages() -> list[dict]:
    return [{"code": c, "label": LANGUAGE_LABELS[c]} for c in SUPPORTED_LANGUAGES]
