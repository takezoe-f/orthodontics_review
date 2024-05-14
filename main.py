import requests
from bs4 import BeautifulSoup
import pandas as pd
import googlemaps
from collections import defaultdict

# 日本矯正歯科学会の公式サイトから認定医リストを取得
def get_doctors_from_page(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    # 名前と所在地を取得
    doctors = []
    table = soup.find('table', class_='tbl_search_roster')  # テーブル要素を見つける
    if table:
        rows = table.find_all('tr')
        for row in rows[1:]:  # ヘッダー行をスキップ
            cols = row.find_all('td')
            if len(cols) > 1:
                qualifications = cols[0].text.strip().replace('\n', ', ')  # 資格をコンマ区切りで結合
                name = cols[1].text.strip()
                zip_code = cols[2].text.strip()
                address = cols[3].text.strip()
                clinic_name = cols[4].text.strip()
                phone = cols[5].text.strip()

                if not name or not address or not clinic_name:
                    continue

                doctors.append({
                    'qualifications': qualifications,
                    'name': name,
                    'zip_code': zip_code,
                    'address': address,
                    'clinic_name': clinic_name,
                    'phone': phone
                })
    return doctors

# ベースURLとページネーションの設定
base_url = 'https://www.jos.gr.jp/page/{}?post_type=roster&s&member_area_code=13&pref=2'
page = 1
all_doctors = []

while True:
    url = base_url.format(page)
    print(f"Fetching data from {url}")
    doctors = get_doctors_from_page(url)
    if not doctors:  # ページにデータがない場合、ループを終了
        break
    all_doctors.extend(doctors)
    page += 1

# DataFrameに変換
df_doctors = pd.DataFrame(all_doctors)
print("Doctors List:")
print(df_doctors.head())  # デバッグ用出力

# Google Maps APIを使用して口コミデータを取得
gmaps = googlemaps.Client(key='AIzaSyAlCaOkhSfapjIdUyZHzNTJ1dg4nA7MTec')

def get_place_reviews(name, address):
    try:
        # 名前が長い場合は、名前の一部を使用して検索精度を向上させる
        if len(name) > 30:
            name = name[:30]
        places_result = gmaps.places(query=name + ' ' + address)
        if places_result['results']:
            print(f"Place found: {places_result['results'][0]['name']} at {places_result['results'][0]['formatted_address']}")  # デバッグ用出力
            place_id = places_result['results'][0]['place_id']
            reviews = gmaps.place(place_id=place_id, fields=['name', 'rating', 'user_ratings_total', 'reviews'])
            return reviews['result']
        else:
            print(f"No place found for {name} in {address}")  # デバッグ用出力
            return None
    except Exception as e:
        print(f"Error fetching data for {name} in {address}: {e}")
        return None

# 口コミの内容、件数、評価に基づいてスコアを計算するロジック
def evaluate_review_quality(review_text):
    if len(review_text) > 200 and ('具体的' in review_text or '詳細' in review_text):
        return 3
    elif len(review_text) > 100:
        return 1
    else:
        return 0

def evaluate_review_count(review_count):
    if review_count >= 50:
        return 3
    elif 20 <= review_count < 50:
        return 2
    elif 10 <= review_count < 20:
        return 1
    else:
        return 0

def evaluate_rating(rating):
    if rating >= 4.5:
        return 3
    elif 4.0 <= rating < 4.5:
        return 2
    elif 3.5 <= rating < 4.0:
        return 1
    else:
        return 0

def calculate_overall_score(reviews, review_count):
    total_score = 0
    for review in reviews:
        text = review.get('text', '')
        rating = review.get('rating', 0)
        total_score += evaluate_review_quality(text) + evaluate_review_count(review_count) + evaluate_rating(rating)
    return total_score / len(reviews) if reviews else 0

# 一定基準以上の口コミをフィルタリングしてリストに追加
high_rated_doctors = defaultdict(list)

for index, row in df_doctors.iterrows():
    name = row['clinic_name']
    address = row['address']
    if not name or not address:
        continue
    print(f"Fetching reviews for {name} in {address}...")  # デバッグ用出力
    reviews = get_place_reviews(name, address)
    if reviews and 'reviews' in reviews:
        review_count = reviews.get('user_ratings_total', 0)
        score = calculate_overall_score(reviews['reviews'], review_count)
        google_rating = reviews.get('rating', 0)
        if google_rating >= 4.0:  # Googleの口コミ評価が4.0以上の病院のみリストに含める
            high_rated_doctors[(row['name'], name, address)].append({
                'rating': google_rating,
                'total_reviews': review_count,
                'score': score
            })
    else:
        print(f"No reviews found for {name} in {address}")

# 病院毎にスコアを集計
final_high_rated_doctors = []

for key, reviews in high_rated_doctors.items():
    name, clinic_name, address = key
    total_score = sum(review['score'] for review in reviews) / len(reviews)
    total_reviews = sum(review['total_reviews'] for review in reviews)
    google_rating = sum(review['rating'] for review in reviews) / len(reviews)
    final_high_rated_doctors.append({
        'name': name,
        'clinic_name': clinic_name,
        'address': address,
        'google_rating': google_rating,
        'total_score': total_score,
        'total_reviews': total_reviews
    })

# DataFrameに変換
df_final_high_rated = pd.DataFrame(final_high_rated_doctors)
print("Final High Rated Doctors List:")
print(df_final_high_rated.head())  # デバッグ用出力

# スコアとGoogle口コミ点数をExcelとCSVに出力
df_final_high_rated.to_excel('high_rated_orthodontists_scores.xlsx', index=False)
df_final_high_rated.to_csv('high_rated_orthodontists_scores.csv', index=False)
print("Excel and CSV output complete.")
