from flask import Flask, render_template, request, redirect, session, url_for, flash, get_flashed_messages
from datetime import datetime
import requests
import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

app = Flask(__name__)
app.secret_key = 'uINS49ystT4h4zC27OuYOIHELXI'
GOOGLE_API_KEY = 'AIzaSyAbzz0kK9mYimlZGv4Zm1GLhmRdCDfPo3s'

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("SUPABASE_URL or SUPABASE_KEY is not set")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

type_descriptions = {
    'restaurant': 'Kuliner', 'cafe': 'Kuliner', 'bakery': 'Kuliner',
    'park': 'Alam', 'zoo': 'Alam', 'natural_feature': 'Alam',
    'tourist_attraction': 'Budaya', 'museum': 'Budaya', 'art_gallery': 'Budaya',
    'church': 'Budaya', 'hindu_temple': 'Budaya', 'library': 'Budaya', 'bar': 'Budaya',
    'shopping_mall': 'Belanja', 'clothing_store': 'Belanja',
    'shoe_store': 'Belanja', 'store': 'Belanja'
}

def get_photo_url(photo_reference, maxwidth=400):
    if not photo_reference:
        return None
    return f"https://maps.googleapis.com/maps/api/place/photo?maxwidth={maxwidth}&photoreference={photo_reference}&key={GOOGLE_API_KEY}"

def get_destinasi(place_id):
    detail_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=name,rating,formatted_address,photos,geometry,types,opening_hours&key={GOOGLE_API_KEY}"
    response = requests.get(detail_url).json()
    result = response.get('result', {})
    deskripsi = next((type_descriptions[t] for t in result.get('types', []) if t in type_descriptions), 'Tempat')
    photo_urls = [get_photo_url(p.get('photo_reference')) for p in result.get('photos', []) if p.get('photo_reference')]
    jam_buka = result.get('opening_hours', {}).get('weekday_text', [])
    buka_sekarang = result.get('opening_hours', {}).get('open_now', None)
    return {
        'id': place_id,
        'nama': result.get('name'),
        'alamat': result.get('formatted_address'),
        'rating': result.get('rating'),
        'lokasi': result.get('geometry', {}).get('location'),
        'deskripsi': deskripsi,
        'foto_urls': photo_urls,
        'jam_buka': jam_buka,
        'buka_sekarang': buka_sekarang
    }

def get_komentar(place_id):
    data = supabase.from_('komentar').select('komentar,tanggal,users(username)').eq('place_id', place_id).order('tanggal', desc=True).execute()
    return data.data

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        kota = request.form['kota']
        kategori_input = request.form['kategori']
        kategori_mapping = {
            'alam': ['park', 'zoo', 'natural_feature'],
            'budaya': ['tourist_attraction', 'museum', 'art_gallery', 'church', 'hindu_temple', 'library', 'bar'],
            'kuliner': ['restaurant', 'cafe', 'bakery'],
            'belanja': ['shopping_mall', 'clothing_store', 'shoe_store', 'store']
        }

        geo_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={kota}&key={GOOGLE_API_KEY}"
        geo_response = requests.get(geo_url).json()
        if not geo_response['results']:
            return render_template('filter.html', error="Kota tidak ditemukan")
        location = geo_response['results'][0]['geometry']['location']
        lat, lng = location['lat'], location['lng']
        radius_meter = 10000
        destinasi = []
        seen_place_ids = set()

        query = f"{kategori_input} di {kota}"
        text_url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={query}&key={GOOGLE_API_KEY}"
        text_results = requests.get(text_url).json().get('results', [])
        for place in text_results:
            place_id = place.get('place_id')
            if not place_id or place_id in seen_place_ids:
                continue
            if place.get('rating', 0) < 4.0:
                continue
            foto_urls = [get_photo_url(p.get('photo_reference')) for p in place.get('photos', []) if p.get('photo_reference')]
            if not foto_urls:
                continue
            destinasi.append({
                'nama': place.get('name'),
                'alamat': place.get('formatted_address'),
                'rating': place.get('rating'),
                'id': place_id,
                'foto_urls': foto_urls
            })
            seen_place_ids.add(place_id)

        for kategori in kategori_mapping.get(kategori_input, []):
            place_url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={lat},{lng}&radius={radius_meter}&type={kategori}&key={GOOGLE_API_KEY}"
            for place in requests.get(place_url).json().get('results', []):
                place_id = place.get('place_id')
                if not place_id or place_id in seen_place_ids:
                    continue
                if place.get('rating', 0) < 4.0:
                    continue
                foto_urls = [get_photo_url(p.get('photo_reference')) for p in place.get('photos', []) if p.get('photo_reference')]
                if not foto_urls:
                    continue
                destinasi.append({
                    'nama': place.get('name'),
                    'alamat': place.get('vicinity'),
                    'rating': place.get('rating'),
                    'id': place_id,
                    'foto_urls': foto_urls
                })
                seen_place_ids.add(place_id)
        return render_template('results.html', destinasi=destinasi)
    return render_template('filter.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        supabase.table('users').insert({"username": username, "email": email, "password": password}).execute()
        return redirect('/login')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        result = supabase.from_('users').select('*').eq('username', username).eq('password', password).single().execute()
        user = result.data
        if user:
            session['username'] = user['username']
            session['user_id'] = user['id']
            return redirect(url_for('home'))
        else:
            return render_template('login.html', error="Username atau password salah")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


# Wishlist page
@app.route('/wishlist')
def wishlist():
    if 'user_id' not in session:
        flash("Anda harus login untuk melihat wishlist.")
        return redirect(url_for('login'))
    result = supabase.from_('wishlist').select('*').eq('user_id', session['user_id']).execute()
    items = result.data
    return render_template('wishlist.html', items=items)

# Add to wishlist
@app.route('/add_wishlist', methods=['POST'])
def add_wishlist():
    if 'user_id' not in session:
        flash("Anda harus login untuk menambahkan ke wishlist.")
        return redirect(url_for('login'))
    place_id = request.form['place_id']
    place_name = request.form['place_name']
    place_address = request.form['place_address']
    # Cek apakah sudah ada
    existing = supabase.from_('wishlist').select('*').eq('user_id', session['user_id']).eq('place_id', place_id).execute().data
    if existing:
        flash("Tempat sudah ada di wishlist.")
    else:
        supabase.table('wishlist').insert({
            "user_id": session['user_id'],
            "place_id": place_id,
            "place_name": place_name,
            "place_address": place_address
        }).execute()
        flash("Berhasil ditambahkan ke wishlist!")
    return redirect(url_for('wishlist'))

# Delete from wishlist
@app.route('/wishlist/delete/<int:wishlist_id>', methods=['POST'])
def delete_wishlist(wishlist_id):
    if 'user_id' not in session:
        flash("Anda harus login untuk menghapus dari wishlist.")
        return redirect(url_for('login'))
    supabase.table('wishlist').delete().eq('id', wishlist_id).eq('user_id', session['user_id']).execute()
    flash("Wishlist berhasil dihapus.")
    return redirect(url_for('wishlist'))

@app.route('/random_place')
def random_place():
    result = supabase.from_('wisata_random').select('*').order('id', desc=False).limit(1).execute()
    tempat = result.data[0] if result.data else None
    if not tempat:
        flash("Belum ada data random wisata.")
        return redirect(url_for('home'))
    place_id = tempat['place_id']
    # Ambil detail dari Google
    detail_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=name,rating,formatted_address,geometry,photos,types,opening_hours&key={GOOGLE_API_KEY}"
    response = requests.get(detail_url).json()
    result_g = response.get('result', {})
    types = result_g.get('types', [])
    kategori_db = tempat.get('kategori')
    kategori_mapped = next((type_descriptions[t] for t in types if t in type_descriptions), 'Tempat')
    kategori = kategori_db if kategori_db else kategori_mapped
    deskripsi = tempat.get('deskripsi') if tempat.get('deskripsi') else kategori
    opening_hours = result_g.get('opening_hours', {})
    jam_buka = opening_hours.get('weekday_text', ["Buka setiap hari"])
    buka_sekarang = opening_hours.get('open_now')
    foto_urls = [get_photo_url(photo.get('photo_reference')) for photo in result_g.get('photos', []) if photo.get('photo_reference')]
    destinasi = {
        'id': place_id,
        'nama': result_g.get('name'),
        'alamat': result_g.get('formatted_address'),
        'rating': result_g.get('rating'),
        'lokasi': result_g.get('geometry', {}).get('location'),
        'deskripsi': deskripsi,
        'kategori': kategori,
        'foto_urls': foto_urls,
        'jam_buka': jam_buka,
        'buka_sekarang': buka_sekarang
    }
    return render_template('detail.html', destinasi=destinasi)
# Route untuk location dan comments agar tidak error di halaman detail
@app.route('/location/<place_id>')
def location(place_id):
    destinasi = get_destinasi(place_id)
    return render_template('location.html', destinasi=destinasi, api_key=GOOGLE_API_KEY)

@app.route('/comments/<place_id>', methods=['GET', 'POST'])
def comments(place_id):
    if request.method == 'POST':
        if 'username' not in session or 'user_id' not in session:
            flash("Anda harus login untuk mengirim komentar.")
            return redirect(url_for('login'))
        komentar_baru = request.form.get('komentar', '').strip()
        if komentar_baru:
            tanggal = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            user_id = session['user_id']
            supabase.table('komentar').insert({
                "user_id": user_id,
                "place_id": place_id,
                "komentar": komentar_baru,
                "tanggal": tanggal
            }).execute()
            flash("Komentar berhasil dikirim!")
        else:
            flash("Komentar tidak boleh kosong.")
        return redirect(url_for('comments', place_id=place_id))
    komentar = get_komentar(place_id)
    destinasi = get_destinasi(place_id)
    return render_template('comments.html', destinasi=destinasi, komentar=komentar, messages=get_flashed_messages())

@app.route('/search', methods=['POST'])
def search():
    query = request.form.get('query', '').strip()
    if not query:
        flash("Masukkan nama destinasi yang ingin dicari.")
        return redirect(url_for('home'))
    search_url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={query}&key={GOOGLE_API_KEY}"
    response = requests.get(search_url).json()
    results = response.get('results', [])
    destinasi = []
    seen_place_ids = set()
    for place in results:
        place_id = place.get('place_id')
        if not place_id or place_id in seen_place_ids:
            continue
        if place.get('rating', 0) < 4.0:
            continue
        foto_urls = [get_photo_url(p.get('photo_reference')) for p in place.get('photos', []) if p.get('photo_reference')]
        if not foto_urls:
            continue
        destinasi.append({
            'nama': place.get('name'),
            'alamat': place.get('formatted_address'),
            'rating': place.get('rating'),
            'id': place_id,
            'foto_urls': foto_urls
        })
        seen_place_ids.add(place_id)
    return render_template('results.html', destinasi=destinasi, query=query)

@app.route('/detail/<place_id>', methods=['GET', 'POST'])
def detail(place_id):
    destinasi = get_destinasi(place_id)
    if request.method == 'POST' and 'username' in session:
        komentar = request.form['komentar']
        user_id = session['user_id']
        tanggal = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        supabase.table('komentar').insert({
            "user_id": user_id,
            "place_id": place_id,
            "komentar": komentar,
            "tanggal": tanggal
        }).execute()
    komentar = get_komentar(place_id)
    return render_template('detail.html', destinasi=destinasi, komentar=komentar)

@app.route('/photo/<place_id>')
def photo(place_id):
    destinasi = get_destinasi(place_id)
    return render_template('photo.html', destinasi=destinasi)

# Run hanya sekali!
if __name__ == '__main__':
    app.run(debug=True)
