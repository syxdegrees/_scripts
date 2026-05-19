#!/usr/bin/env python3
"""
Merges Google Maps Places API types (existing JSON) with
Google My Business categories from daltonluka.com.
Outputs a merged, sorted google_maps_categories.json.
"""

import json
import re
import sys
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
OUT_FILE = SCRIPT_DIR / "google_maps_categories.json"


def fetch_gmb_labels():
    url = "https://daltonluka.com/blog/google-my-business-categories"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    items = re.findall(r"<li>(.*?)</li>", html, re.DOTALL)
    labels = set()
    for item in items:
        text = re.sub(r"<[^>]+>", "", item).strip()
        if text and len(text) > 2 and "\n" not in text:
            labels.add(text)
    return labels


def label_to_type(label):
    t = label.lower()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    t = re.sub(r"\s+", "_", t.strip())
    return t


KEYWORD_RULES = [
    (["restaurant", " bar", "cafe", "bakery", "brewery", "brewpub", "bistro",
      "diner", "food court", "pub", "pizzeria", "buffet", "eatery", "taproom",
      "steakhouse", "sushi", "ramen", "noodle", "dim sum", "izakaya",
      "confectionery", "pastry", "donut", "bagel", "juice", "smoothie",
      "ice cream", "gelato", "chocolat", "candy", "wine bar", "winery",
      "cocktail", "tapas", "delicatessen", "deli ", "snack", "takeout",
      "takeaway", "meal delivery", "fast food", "tea room", "tea house"],
     "Food and Drink"),
    (["grocery", "supermarket", "hypermarket", "department store", "clothing store",
      "shoe store", "bookstore", "book store", "electronics store", "furniture store",
      "hardware store", "pet store", "toy store", "jewel", "apparel", "boutique",
      "thrift", "gift shop", "florist", "garden center", "market ", "shopping mall",
      "liquor store", "convenience store", "pharmacy", "drug store", "drugstore",
      "home goods", "sporting goods", "music store", "art supply", "craft store",
      "fabric store", "baby store", "cosmetics", "beauty supply", "wholesale",
      "wholesaler", "outlet store", "pawn shop", "antique", "second hand",
      "surplus store", " dealer", "supplier", "supply store", " shop ", "store"],
     "Shopping"),
    (["contractor", "plumber", "electrician", "hvac", "roofing", "painter",
      "cleaning service", "landscaping", "lawn", "pest control", "locksmith",
      "moving company", "storage", "courier", "shipping", "repair service",
      "installation", "maintenance service", "handyman", "upholstery",
      "alterations", "tailor", "laundry", "dry clean", "window cleaning",
      "chimney", "gutter", "fence", "paving", "concrete", "demolition",
      "excavating", "welding", "septic", "drainage", "waterproofing",
      "insulation", "drywall", "flooring", "tiling", "carpentry", "cabinet",
      "pool service", "irrigation", "tree service", "snow removal",
      "garbage", "waste", "recycling", "exterminator", "fumigation",
      "surveyor", "testing service", "inspection", "notary", "printing",
      "sign ", "advertising", "marketing", "media", "staffing", "recruiter",
      "employment", "cleaning", "janitorial", "security service", "guard",
      "private investigator", "courier", "delivery service", "driver",
      "freight", "logistics", "warehouse", "fulfillment", "translat",
      "interpret", "transcription", "catering", "event planning", "wedding",
      "photography", "videograph", "graphic design", "web design", "IT ",
      "computer repair", "software", "consulting", "accountant", "bookkeeping",
      "tax ", "insurance", "real estate", "mortgage", "title company",
      "escrow", "property management", "property maintenance",
      "architect", "engineer", "surveying", "environmental",
      "legal", "attorney", "lawyer", "notary"],
     "Services"),
    (["hospital", "clinic", "medical", "doctor", "physician", "surgeon",
      "dentist", "dental", "orthodont", "optometrist", "optician", "eye care",
      "vision center", "chiropractor", "physical therap", "occupational therap",
      "speech therap", "mental health", "psychiatr", "psycholog", "counseling",
      "therapist", "acupuncture", "massage", "spa", "wellness", "yoga",
      "pilates", "nutrition", "dietitian", "pharmacy", "drugstore", "drug store",
      "urgent care", "emergency", "ambulance", "blood bank", "dialysis",
      "fertility", "oncolog", "cardiolog", "dermatolog", "neurolog",
      "orthopedic", "pediatric", "geriatric", "rehab", "nursing",
      "assisted living", "hospice", "home health", "midwife", "lactation",
      "audiolog", "hearing", "sleep center"],
     "Health and Wellness"),
    (["school", "university", "college", "academy", "institute", "tutoring",
      "learning center", "preschool", "kindergarten", "elementary", "high school",
      "middle school", "vocational", "trade school", "driving school",
      "music school", "dance school", "art school", "cooking school",
      "language school", "flight school", "swim school", "martial arts school",
      "library", "education"],
     "Education"),
    (["church", "chapel", "cathedral", "basilica", "temple", "mosque",
      "synagogue", "shrine", "ashram", "monastery", "convent", "abbey",
      "worship", "religious", "islamic", "jewish", "hindu", "buddhist",
      "christian", "catholic", "protestant", "orthodox", "baptist",
      "methodist", "lutheran", "presbyterian", "episcopal"],
     "Places of Worship"),
    (["hotel", "motel", "inn ", "hostel", "bed and breakfast", "resort",
      "campground", "camping", "cottage", "cabin ", "vacation rental",
      "guest house", "lodging", "rv park", "mobile home"],
     "Lodging"),
    (["car dealer", "auto dealer", "car rental", "car wash", "auto repair",
      "auto body", "tire ", "oil change", "car detailing", "towing",
      "transmission", "brake", "muffler", "windshield", "car audio",
      "motorcycle dealer", "motorcycle repair", "rv dealer", "rv repair",
      "truck dealer", "truck rental", "parking", "gas station", "ev charging",
      "electric vehicle", "vehicle inspection", "smog"],
     "Automotive"),
    (["gym", "fitness", "sports club", "athletic", "swimming pool",
      "tennis court", "golf course", "bowling", "yoga studio", "pilates studio",
      "martial arts", "boxing", "wrestling", "football", "soccer", "basketball",
      "baseball", "softball", "volleyball", "hockey", "lacrosse", "rugby",
      "cricket", "squash court", "racquetball", "badminton", "rock climbing",
      "bouldering", "archery", "equestrian", "horseback", "skating",
      "roller skating", "ski ", "snowboard", "surfing", "kayak", "canoe",
      "cycling", "bicycle club", "running", "track", "stadium", "arena",
      "sports complex", "sports center"],
     "Sports"),
    (["museum", "gallery", "theater", "theatre", "cinema", "movie",
      "concert hall", "opera", "ballet", "performing arts", "comedy club",
      "escape room", "arcade", "amusement", "theme park", "water park",
      "zoo", "aquarium", "botanical", "garden", "park ", "playground",
      "night club", "nightclub", "karaoke", "bowling", "casino",
      "entertainment", "recreation center", "community center",
      "cultural center", "heritage", "historical", "monument",
      "tourist attraction", "visitor center", "event venue"],
     "Entertainment and Recreation"),
    (["airport", "train station", "bus station", "subway", "metro",
      "transit", "ferry", "taxi", "rideshare", "car service", "limo",
      "transportation", "moving service", "shipping", "port", "harbor",
      "marina", "heliport", "truck stop"],
     "Transportation"),
    (["bank", "credit union", "atm", "financial", "investment", "stock broker",
      "insurance ", "mortgage broker", "loan", "currency exchange",
      "accounting firm", "tax preparer", "auditor", "pawnbroker"],
     "Finance"),
    (["city hall", "government", "police", "fire station", "court",
      "embassy", "consulate", "post office", "dmv", "social services",
      "public library", "military", "national guard", "border"],
     "Government"),
]


def assign_category(label):
    lower = label.lower()
    for keywords, cat in KEYWORD_RULES:
        for kw in keywords:
            if kw in lower:
                return cat
    return "Other"


def main():
    print("Fetching GMB categories...", flush=True)
    gmb_labels = fetch_gmb_labels()
    print(f"  {len(gmb_labels)} categories found on page")

    print("Loading existing JSON...", flush=True)
    with open(OUT_FILE, encoding="utf-8") as f:
        existing = json.load(f)
    print(f"  {len(existing)} existing entries")

    existing_lower = {e["label"].lower() for e in existing}

    new_entries = []
    for label in sorted(gmb_labels):
        if label.lower() not in existing_lower:
            new_entries.append({
                "type": label_to_type(label),
                "label": label,
                "category": assign_category(label),
            })

    print(f"  {len(new_entries)} new entries to add")

    merged = existing + new_entries
    # Sort by category then label
    merged.sort(key=lambda e: (e["category"], e["label"].lower()))

    with open(OUT_FILE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"Done. Wrote {len(merged)} total entries to {OUT_FILE}")


if __name__ == "__main__":
    main()
