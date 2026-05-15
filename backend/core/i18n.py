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
    # ---------- Post-expiry recovery nudges (day 1 / 3 / 7) ----------
    # `{stage_label}` is supplied by the caller as a localized urgency phrase below;
    # `{days_overdue}` is the integer number of days past valid_until.
    "subscription_recovery": {
        "en": "{stage_label} — {school_name}: your SCMS subscription expired {days_overdue} day(s) ago. {action_line} Renew at {renew_url}.",
        "hi": "{stage_label} — {school_name}: आपकी SCMS सदस्यता को {days_overdue} दिन हो गए हैं। {action_line} {renew_url} पर रिन्यू करें।",
        "ta": "{stage_label} — {school_name}: உங்கள் SCMS சந்தா {days_overdue} நாட்களாக காலாவதியாகியுள்ளது. {action_line} {renew_url} இல் புதுப்பிக்கவும்.",
        "te": "{stage_label} — {school_name}: మీ SCMS సబ్‌స్క్రిప్షన్ {days_overdue} రోజుల క్రితం ముగిసింది. {action_line} {renew_url} వద్ద పునరుద్ధరించండి.",
        "kn": "{stage_label} — {school_name}: ನಿಮ್ಮ SCMS ಚಂದಾದಾರಿಕೆ {days_overdue} ದಿನಗಳ ಹಿಂದೆ ಮುಗಿದಿದೆ. {action_line} {renew_url} ನಲ್ಲಿ ನವೀಕರಿಸಿ.",
        "mr": "{stage_label} — {school_name}: तुमची SCMS सदस्यता {days_overdue} दिवसांपूर्वी संपली. {action_line} {renew_url} वर नूतनीकरण करा.",
        "bn": "{stage_label} — {school_name}: আপনার SCMS সাবস্ক্রিপশন {days_overdue} দিন আগে শেষ হয়েছে। {action_line} {renew_url} এ নবায়ন করুন।",
        "gu": "{stage_label} — {school_name}: તમારી SCMS સબ્સ્ક્રિપ્શન {days_overdue} દિવસ પહેલા સમાપ્ત થઈ. {action_line} {renew_url} પર નવીકરણ કરો.",
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


# Stage 1 = day 1 (friendly), 2 = day 3 (action), 3 = day 7+ (final/locked).
RECOVERY_STAGE_LABEL = {
    1: {"en": "Friendly reminder", "hi": "मित्रवत अनुस्मारक", "ta": "நட்பான நினைவூட்டல்",
        "te": "స్నేహపూర్వక గుర్తుచేత", "kn": "ಸ್ನೇಹಪರ ಜ್ಞಾಪನೆ", "mr": "मैत्रीपूर्ण आठवण",
        "bn": "বন্ধুত্বপূর্ণ স্মরণ", "gu": "મિત્રતાભર્યું સ્મરણ"},
    2: {"en": "Action needed", "hi": "कार्रवाई आवश्यक", "ta": "நடவடிக்கை தேவை",
        "te": "చర్య అవసరం", "kn": "ಕ್ರಮ ಅಗತ್ಯವಿದೆ", "mr": "कार्यवाही आवश्यक",
        "bn": "পদক্ষেপ প্রয়োজন", "gu": "પગલાં જરૂરી"},
    3: {"en": "Final notice", "hi": "अंतिम सूचना", "ta": "இறுதி அறிவிப்பு",
        "te": "చివరి నోటీసు", "kn": "ಅಂತಿಮ ಸೂಚನೆ", "mr": "अंतिम सूचना",
        "bn": "চূড়ান্ত নোটিশ", "gu": "અંતિમ સૂચના"},
}

RECOVERY_ACTION_LINE = {
    1: {"en": "Your grace period is still on — please renew to avoid any interruption.",
        "hi": "आपकी छूट अवधि अभी सक्रिय है — किसी रुकावट से बचने के लिए कृपया रिन्यू करें।",
        "ta": "உங்கள் சலுகை காலம் இன்னும் செயலில் உள்ளது — தடைகள் இல்லாமல் இருக்க புதுப்பிக்கவும்.",
        "te": "మీ గ్రేస్ పీరియడ్ ఇంకా ఆన్ ఉంది — అంతరాయం లేకుండా ఉండడానికి పునరుద్ధరించండి.",
        "kn": "ನಿಮ್ಮ ಕೃಪಾ ಅವಧಿ ಇನ್ನೂ ಚಾಲ್ತಿಯಲ್ಲಿದೆ — ಯಾವುದೇ ಅಡಚಣೆ ತಪ್ಪಿಸಲು ನವೀಕರಿಸಿ.",
        "mr": "तुमचा सवलत कालावधी अजून सुरू आहे — व्यत्यय टाळण्यासाठी कृपया नूतनीकरण करा.",
        "bn": "আপনার গ্রেস পিরিয়ড এখনও চালু আছে — কোনও বাধা এড়াতে দয়া করে নবায়ন করুন।",
        "gu": "તમારી ગ્રેસ પીરિયડ હજુ ચાલુ છે — કોઈપણ વિક્ષેપ ટાળવા માટે કૃપા કરી નવીકરણ કરો."},
    2: {"en": "Write actions will be blocked tomorrow if you don't renew.",
        "hi": "यदि आप कल तक रिन्यू नहीं करते हैं, तो लिखने की कार्रवाइयां रोक दी जाएंगी।",
        "ta": "நாளை வரை புதுப்பிக்கவில்லை என்றால் எழுத்து செயல்கள் தடுக்கப்படும்.",
        "te": "మీరు పునరుద్ధరించకపోతే రేపటి నుంచి రాత చర్యలు బ్లాక్ చేయబడతాయి.",
        "kn": "ನೀವು ನವೀಕರಿಸದಿದ್ದರೆ ನಾಳೆಯಿಂದ ಬರೆಯುವ ಕ್ರಿಯೆಗಳು ನಿರ್ಬಂಧಿಸಲಾಗುತ್ತದೆ.",
        "mr": "तुम्ही उद्यापर्यंत नूतनीकरण न केल्यास लिहिण्याच्या क्रिया अवरोधित केल्या जातील.",
        "bn": "আপনি যদি কাল পর্যন্ত নবায়ন না করেন, লেখার কার্যক্রম ব্লক হয়ে যাবে।",
        "gu": "જો તમે કાલ સુધી નવીકરણ ન કરો તો લખવાની ક્રિયાઓ બ્લોક થઈ જશે."},
    3: {"en": "Your school is now read-only. Teachers can't mark attendance or enter marks until you renew.",
        "hi": "आपका स्कूल अब केवल-पठनीय है। रिन्यू करने तक शिक्षक उपस्थिति या अंक दर्ज नहीं कर सकते।",
        "ta": "உங்கள் பள்ளி இப்போது படிக்க மட்டுமே. புதுப்பிக்கும் வரை ஆசிரியர்கள் வருகை அல்லது மதிப்பெண்களை பதிய முடியாது.",
        "te": "మీ స్కూల్ ఇప్పుడు రీడ్-ఓన్లీ. మీరు పునరుద్ధరించే వరకు టీచర్లు హాజరు లేదా మార్కులు నమోదు చేయలేరు.",
        "kn": "ನಿಮ್ಮ ಶಾಲೆ ಈಗ ಓದಲು ಮಾತ್ರ. ನೀವು ನವೀಕರಿಸುವವರೆಗೆ ಶಿಕ್ಷಕರು ಹಾಜರಾತಿ ಅಥವಾ ಅಂಕಗಳನ್ನು ನಮೂದಿಸಲಾಗದು.",
        "mr": "तुमची शाळा आता फक्त-वाचनीय आहे. नूतनीकरण होईपर्यंत शिक्षक उपस्थिती किंवा गुण नोंदवू शकत नाहीत.",
        "bn": "আপনার স্কুল এখন শুধুমাত্র পড়ার জন্য। নবায়ন না হওয়া পর্যন্ত শিক্ষকরা উপস্থিতি বা নম্বর প্রবেশ করতে পারবেন না।",
        "gu": "તમારી શાળા હવે ફક્ત-વાંચન છે. નવીકરણ થાય ત્યાં સુધી શિક્ષકો હાજરી અથવા ગુણ દાખલ કરી શકતા નથી."},
}


def render_recovery(stage: int, lang: str | None, **kwargs: Any) -> str:
    """Render the subscription_recovery template with the stage-specific label + action line.

    `stage` is 1 (day-1, friendly), 2 (day-3, urgent), or 3 (day-7+, final/locked).
    """
    lang = (lang or "en").lower()
    label = RECOVERY_STAGE_LABEL.get(stage, RECOVERY_STAGE_LABEL[1]).get(lang) \
        or RECOVERY_STAGE_LABEL[stage]["en"]
    action = RECOVERY_ACTION_LINE.get(stage, RECOVERY_ACTION_LINE[1]).get(lang) \
        or RECOVERY_ACTION_LINE[stage]["en"]
    return render("subscription_recovery", lang, stage_label=label, action_line=action, **kwargs)
