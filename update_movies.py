import os
import re
import time
import requests

SUPABASE_URL = "https://rtsmuwuwvvdcmzcboarq.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")

TARGET_TABLES = [
    {"name": "movies_cima", "title": "title", "desc": "description", "rating": "rating", "poster": "poster_url"},
    {"name": "arabic_movies", "title": "title", "desc": "description", "rating": "rating", "poster": "poster_url"},
    {"name": "tv_series", "title": "title", "desc": "description", "rating": "rating", "poster": "poster_url"}
]

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

def clean_movie_title(raw_title):
    if not raw_title:
        return ""
    
    title = re.sub(r'\b(19|20)\d{2}\b', '', raw_title)
    title = re.sub(r'[()\[\]{}]', ' ', title)
    title = re.sub(r'[-–—|:]', ' ', title)
    title = re.sub(r'\b(عرض|ترجمه|مدبلج|كامل|HD|1080p|720p|4K|اون|لاين|مترجم)\b', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+', ' ', title)
    
    return title.strip()

def process_table(table_info):
    table_name = table_info["name"]
    col_title = table_info["title"]
    col_desc = table_info["desc"]
    col_rating = table_info["rating"]
    col_poster = table_info["poster"]

    print(f"\n--- البدء في فحص ومعالجة جدول: {table_name} بالكامل ---", flush=True)

    batch_number = 1
    while True:
        # جلب العناصر التي لم تتم معالجتها بعد (tmbd = false)
        url = f"{SUPABASE_URL}/rest/v1/{table_name}?select=id,{col_title},{col_desc},{col_poster}&tmbd=eq.false&limit=1000"
        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            print(f"فشل جلب البيانات من جدول {table_name}: {response.text}", flush=True)
            break

        items = response.json()
        if not items:
            print(f"تم الانتهاء من كافة عناصر جدول {table_name} ولم يتبق عناصر بحاجة للتحديث.", flush=True)
            break

        print(f"\n[الدفعة {batch_number}] - تم جلب {len(items)} عنصر غير معالج في {table_name}...", flush=True)

        success_count = 0
        for index, item in enumerate(items, 1):
            item_id = item.get("id")
            raw_title = item.get(col_title)
            
            if not raw_title:
                continue

            search_query = clean_movie_title(raw_title)
            if not search_query:
                search_query = raw_title

            try:
                tmdb_url_ar = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&language=ar-AR&query={requests.utils.quote(search_query)}"
                res_ar = requests.get(tmdb_url_ar).json()

                media_data = None
                found_lang = ""

                if "results" in res_ar and len(res_ar["results"]) > 0:
                    media_data = res_ar["results"][0]
                    found_lang = "بالعربي"

                if not media_data or not media_data.get("overview"):
                    tmdb_url_en = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&language=en-US&query={requests.utils.quote(search_query)}"
                    res_en = requests.get(tmdb_url_en).json()

                    if "results" in res_en and len(res_en["results"]) > 0:
                        media_data = res_en["results"][0]
                        found_lang = "بالإنجليزي"

                # تعيين العمود tmbd ليصبح true عند الانتهاء من محاولة المعالجة
                update_payload = {"tmbd": True}

                if media_data:
                    new_description = media_data.get("overview")
                    new_rating = media_data.get("vote_average")
                    poster_path = media_data.get("poster_path")
                    
                    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

                    if new_description:
                        update_payload[col_desc] = new_description
                    else:
                        update_payload[col_desc] = "لا يوجد وصف متوفر"
                        
                    if new_rating is not None:
                        update_payload[col_rating] = str(round(new_rating, 1))
                        
                    if poster_url:
                        update_payload[col_poster] = poster_url

                else:
                    update_payload[col_desc] = "لا يوجد وصف متوفر"

                update_url = f"{SUPABASE_URL}/rest/v1/{table_name}?id=eq.{item_id}"
                update_res = requests.patch(update_url, headers=headers, json=update_payload)

                if update_res.status_code in [200, 204]:
                    if media_data:
                        poster_msg = "مع بوستر 🖼️" if poster_url else "بدون بوستر ❌"
                        print(f"[{index}/{len(items)}] ✓ تم تحديث ({table_name}) [{found_lang}] ({poster_msg}): {raw_title}", flush=True)
                    else:
                        print(f"[{index}/{len(items)}] ⮭ غير موجود في TMDB وتم تعليمه (تخطي مستقبلاً): {raw_title}", flush=True)
                    success_count += 1
                else:
                    print(f"[{index}/{len(items)}] ✗ خطأ قاعدة بيانات في {table_name}: {update_res.text}", flush=True)

            except Exception as e:
                print(f"[{index}/{len(items)}] ⚠ خطأ مع العنصر {raw_title}: {e}", flush=True)

            time.sleep(0.15)
        
        print(f"انتهت الدفعة {batch_number} من جدول {table_name}. تم معالجة {success_count} من أصل {len(items)} عنصر.", flush=True)
        batch_number += 1

if __name__ == "__main__":
    if not TMDB_API_KEY:
        print("خطأ: مفتاح TMDB غير موجود!", flush=True)
    else:
        print("=== بدء تشغيل السكربت بنظام تخطي العنصر عبر عمود tmbd ===", flush=True)
        for table in TARGET_TABLES:
            process_table(table)
        print("=== تم الانتهاء من كافة الجداول والدفعات بنجاح تام ===", flush=True)
