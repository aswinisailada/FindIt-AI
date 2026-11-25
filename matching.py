import re
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
from PIL import Image
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

BRANDS = {"boat":"boat", "noise":"noise", "jbl":"jbl", "samsung":"samsung", "apple":"apple", "oneplus":"oneplus", "realme":"realme", "redmi":"redmi", "xiaomi":"xiaomi", "sony":"sony", "boult":"boult", "oppo":"oppo", "vivo":"vivo"}
TYPES = {
 "wireless_earbuds":["bluetooth", "bluetooth earbuds", "earbuds", "airpods", "airpod", "airpodes", "airpode", "airdopes", "airdope", "tws", "wireless earbuds", "wireless earphones"],
 "smart_watch":["smart watch", "smartwatch", "fitness watch", "fitness band"],
 "watch":["wrist watch", "wristwatch", "watch"],
 "headphones":["headphones", "headphone", "headset"],
 "mobile_phone":["smartphone", "mobile phone", "mobile", "iphone"],
 "charger":["charger", "adapter"], "wallet":["wallet", "purse"], "bag":["backpack", "handbag", "bag"], "keys":["keys", "keychain", "key"]
}
COLORS = {"black":["black"], "white":["white"], "blue":["blue", "navy"], "red":["red"], "green":["green"], "pink":["pink"], "gray":["gray", "grey"], "silver":["silver"], "gold":["gold"], "brown":["brown"], "purple":["purple", "violet"]}

def clean_value(v):
    if v is None: return ""
    try:
        if pd.isna(v): return ""
    except (TypeError, ValueError): pass
    return re.sub(r"\s+", " ", str(v).strip())

def _text(r):
    return " ".join(clean_value(r.get(k, "")) for k in ("item_name", "description", "category", "color")).lower()

def _has(text, term):
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text))

def _extract_group(text, groups, priority=None):
    for key in (priority or list(groups)):
        for term in sorted(groups[key], key=len, reverse=True):
            if _has(text, term): return key
    return None

def _extract_type(r):
    order = ["smart_watch", "wireless_earbuds", "headphones", "mobile_phone", "charger", "wallet", "bag", "keys", "watch"]
    found = _extract_group(_text(r), TYPES, order)
    if found: return found
    t = _text(r)
    return "wireless_audio" if "bluetooth" in t or "wireless" in t else None

def _extract_color(r):
    for source in (clean_value(r.get("color", "")).lower(), _text(r)):
        found = _extract_group(source, COLORS)
        if found: return found
    return None

def _extract_brand(r):
    return _extract_group(_text(r), {k: [k] for k in BRANDS})

def _extract_model(r):
    t = _text(r)
    patterns = [r"\bairdopes\s*[- ]?(\d{2,4}[a-z]?)\b", r"\bairpods?\s*(?:pro\s*)?(\d{1,2})\b", r"\btune\s*[- ]?(\d{2,4}[a-z]?)\b", r"\b(?:colorfit|color\s*fit)\s*[- ]?([a-z0-9]{2,8})\b", r"\b(?:buds?|watch)\s*[- ]?([a-z]?\d{1,4}[a-z]?)\b"]
    for pattern in patterns:
        m = re.search(pattern, t)
        if m: return m.group(1).lower()
    return None

def text_similarity(a, b):
    a, b = clean_value(a).lower(), clean_value(b).lower()
    if not a or not b: return None
    if a == b: return 1.0
    try:
        v = TfidfVectorizer(ngram_range=(1, 2), stop_words="english").fit_transform([a, b])
        return float(cosine_similarity(v[0:1], v[1:2])[0][0])
    except ValueError: return 0.0

def _same(a, b):
    return None if not a or not b else (1.0 if a == b else 0.0)

def _type_score(a, b):
    if not a or not b: return None
    if a == b: return 1.0
    related = {"wireless_earbuds", "wireless_audio", "headphones"}
    return 0.75 if a in related and b in related else 0.0

def _date(a, b):
    try:
        d1 = datetime.strptime(clean_value(a)[:10], "%Y-%m-%d").date()
        d2 = datetime.strptime(clean_value(b)[:10], "%Y-%m-%d").date()
        return max(0.0, 1.0 - abs((d1-d2).days)/30.0)
    except (ValueError, TypeError): return None

def _location(a, b):
    stop = {"room", "number", "no", "near", "opposite", "and"}
    aa = {x for x in re.sub(r"[^a-z0-9 ]", " ", clean_value(a).lower()).split() if len(x)>1 and x not in stop}
    bb = {x for x in re.sub(r"[^a-z0-9 ]", " ", clean_value(b).lower()).split() if len(x)>1 and x not in stop}
    return len(aa & bb)/len(aa | bb) if aa and bb else None

def _hash(path):
    if not path: return None
    try:
        p = Path(__file__).resolve().parent / str(path)
        if not p.is_file(): return None
        with Image.open(p) as im: px = np.asarray(im.convert("L").resize((8,8)), dtype=np.float32)
        return px > px.mean()
    except (OSError, ValueError): return None

def image_similarity(a, b):
    x, y = _hash(a), _hash(b)
    return None if x is None or y is None else float(1-np.count_nonzero(x != y)/64)

def calculate_match_details(lost, found):
    typ = _type_score(_extract_type(lost), _extract_type(found))
    col = _same(_extract_color(lost), _extract_color(found))
    brand = _same(_extract_brand(lost), _extract_brand(found))
    model = _same(_extract_model(lost), _extract_model(found))
    c1, c2 = clean_value(lost.get("category", "")).lower(), clean_value(found.get("category", "")).lower()
    cat = _same(c1, c2)
    desc = text_similarity(lost.get("description", ""), found.get("description", ""))
    loc = _location(lost.get("location", ""), found.get("location", ""))
    dt = _date(lost.get("report_date", ""), found.get("report_date", ""))
    img = image_similarity(lost.get("image_path", ""), found.get("image_path", ""))
    main = [("item_type",typ,.20),("color",col,.20),("brand",brand,.20),("model",model,.25),("category",cat,.05)]
    support = [(desc,.50),(loc,.20),(dt,.15),(img,.15)]
    sw = sum(w for v,w in support if v is not None)
    sup = sum(v*w for v,w in support if v is not None)/sw if sw else None
    parts = main + [("other_details",sup,.10)]
    denom = sum(w for _,v,w in parts if v is not None)
    score = sum(v*w for _,v,w in parts if v is not None)/denom*100 if denom else 0
    details = {n:(round(v*100,1) if v is not None else None) for n,v,_ in parts}
    details.update({"description":round(desc*100,1) if desc is not None else None, "location":round(loc*100,1) if loc is not None else None, "date":round(dt*100,1) if dt is not None else None, "image":round(img*100,1) if img is not None else None})
    return round(score,2), details

def calculate_match(lost, found):
    return calculate_match_details(lost, found)[0]
