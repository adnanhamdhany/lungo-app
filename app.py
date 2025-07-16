from flask import Flask, render_template, request, redirect, session, url_for, flash, get_flashed_messages
import mysql.connector
from datetime import datetime
import requests
import os

app = Flask(__name__)
app.secret_key = 'rahasia_lungo'
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')

# Koneksi ke database MySQL
conn = mysql.connector.connect(
    host="34.142.240.31",
    port="3306",
    user="root",
    password="",
    database="lungo-db"
)
cursor = conn.cursor(dictionary=True)

# Mapping tipe tempat Google Places ke deskripsi kategori
type_descriptions = {
    'restaurant': 'Kuliner',
    'cafe': 'Kuliner',
    'bakery': 'Kuliner',
    'park': 'Alam',
    'zoo': 'Alam',
    'natural_feature': 'Alam',
    'tourist_attraction': 'Budaya',
    'museum': 'Budaya',
    'art_gallery': 'Budaya',
    'church': 'Budaya',
    'hindu_temple': 'Budaya',
    'library': 'Budaya',
    'bar': 'Budaya',
    'shopping_mall': 'Belanja',
    'clothing_store': 'Belanja',
    'shoe_store': 'Belanja',
    'store': 'Belanja'
}

def get_photo_url(photo_reference, maxwidth=400):
    if not photo_reference:
        return None
    return (
        f"https://maps.googleapis.com/maps/api/place/photo"
        f"?maxwidth={maxwidth}&photoreference={photo_reference}&key={GOOGLE_API_KEY}"
    )

def get_destinasi(place_id):
    detail_url = (
        f"https://maps.googleapis.com/maps/api/place/details/json"
        f"?place_id={place_id}&fields=name,rating,formatted_address,photos,geometry,types,opening_hours&key={GOOGLE_API_KEY}"
    )
    response = requests.get(detail_url).json()
    result = response.get('result', {})
    deskripsi = next(
        (type_descriptions[t] for t in result.get('types', []) if t in type_descriptions),
        'Tempat'
    )
    photo_urls = [get_photo_url(photo.get('photo_reference')) for photo in result.get('photos', []) if photo.get('photo_reference')]
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
    cursor.execute(
        "SELECT k.komentar, k.tanggal, u.username FROM komentar k JOIN users u ON k.user_id = u.id WHERE k.place_id = %s ORDER BY k.tanggal DESC",
        (place_id,)
    )
    return cursor.fetchall()

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

        # Geocode kota via Google API
        geo_url = (
            f"https://maps.googleapis.com/maps/api/geocode/json"
            f"?address={kota}&key={GOOGLE_API_KEY}"
        )
        geo_response = requests.get(geo_url).json()
        if not geo_response['results']:
            return render_template('filter.html', error="Kota tidak ditemukan")

        location = geo_response['results'][0]['geometry']['location']
        lat, lng = location['lat'], location['lng']

        radius_meter = 10000
        destinasi = []
        seen_place_ids = set()

        # =======================
        # 1. Tempat terkenal dulu
        # =======================
        query = f"{kategori_input} di {kota}"
        text_url = (
            f"https://maps.googleapis.com/maps/api/place/textsearch/json"
            f"?query={query}&key={GOOGLE_API_KEY}"
        )
        text_response = requests.get(text_url).json()
        text_results = text_response.get('results', [])

        for place in text_results:
            place_id = place.get('place_id')
            if not place_id or place_id in seen_place_ids:
                continue

            rating = place.get('rating', 0)
            if rating < 4.0:
                continue

            photos = place.get('photos', [])
            foto_urls = [get_photo_url(photo.get('photo_reference')) for photo in photos if photo.get('photo_reference')]
            if not foto_urls:
                continue

            destinasi.append({
                'nama': place.get('name'),
                'alamat': place.get('formatted_address'),
                'rating': rating,
                'id': place_id,
                'foto_urls': foto_urls
            })
            seen_place_ids.add(place_id)

        # ===============================
        # 2. Tambahan dari Nearby Search
        # ===============================
        for kategori in kategori_mapping.get(kategori_input, []):
            place_url = (
                f"https://maps.googleapis.com/maps/api/place/nearbysearch/json"
                f"?location={lat},{lng}&radius={radius_meter}&type={kategori}&key={GOOGLE_API_KEY}"
            )
            place_response = requests.get(place_url).json()
            nearby_results = place_response.get('results', [])

            for place in nearby_results:
                place_id = place.get('place_id')
                if not place_id or place_id in seen_place_ids:
                    continue

                rating = place.get('rating', 0)
                if rating < 4.0:
                    continue

                photos = place.get('photos', [])
                foto_urls = [get_photo_url(photo.get('photo_reference')) for photo in photos if photo.get('photo_reference')]
                if not foto_urls:
                    continue

                destinasi.append({
                    'nama': place.get('name'),
                    'alamat': place.get('vicinity'),
                    'rating': rating,
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
        cursor.execute(
            "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
            (username, email, password)
        )
        conn.commit()
        return redirect('/login')
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cursor.execute(
            "SELECT * FROM users WHERE username=%s AND password=%s",
            (username, password)
        )
        user = cursor.fetchone()
        if user:
            session['username'] = user['username']
            session['user_id'] = user['id']
            return redirect(url_for('home'))
        else:
            error = "Username atau password salah"
            return render_template('login.html', error=error)
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


@app.route('/detail/<place_id>', methods=['GET', 'POST'])
def detail(place_id):
    destinasi = get_destinasi(place_id)

    if request.method == 'POST' and 'username' in session:
        komentar = request.form['komentar']
        user_id = session['user_id']
        tanggal = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            "INSERT INTO komentar (user_id, place_id, komentar, tanggal) VALUES (%s, %s, %s, %s)",
            (user_id, place_id, komentar, tanggal)
        )
        conn.commit()

    komentar = get_komentar(place_id)
    return render_template('detail.html', destinasi=destinasi, komentar=komentar)


@app.route('/photo/<place_id>')
def photo(place_id):
    destinasi = get_destinasi(place_id)
    return render_template('photo.html', destinasi=destinasi)


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
            cursor.execute(
                "INSERT INTO komentar (user_id, place_id, komentar, tanggal) VALUES (%s, %s, %s, %s)",
                (user_id, place_id, komentar_baru, tanggal)
            )
            conn.commit()
            flash("Komentar berhasil dikirim!")
        else:
            flash("Komentar tidak boleh kosong.")
        return redirect(url_for('comments', place_id=place_id))

    komentar = get_komentar(place_id)
    destinasi = get_destinasi(place_id)
    return render_template('comments.html', destinasi=destinasi, komentar=komentar, messages=get_flashed_messages())


@app.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'POST':
        query = request.form.get('query', '').strip()
    else:
        query = request.args.get('query', '').strip()

    # if not query:
    #     flash("Masukkan nama destinasi yang ingin dicari.")
    #     return redirect(url_for('home'))

    search_url = (
        f"https://maps.googleapis.com/maps/api/place/textsearch/json"
        f"?query={query}&key={GOOGLE_API_KEY}"
    )
    response = requests.get(search_url).json()
    results = response.get('results', [])

    destinasi = []
    seen_place_ids = set()

    for place in results:
        place_id = place.get('place_id')
        if not place_id or place_id in seen_place_ids:
            continue

        rating = place.get('rating', 0)
        if rating < 4.0:
            continue

        photos = place.get('photos', [])
        foto_urls = [get_photo_url(photo.get('photo_reference')) for photo in photos if photo.get('photo_reference')]
        if not foto_urls:
            continue

        destinasi.append({
            'nama': place.get('name'),
            'alamat': place.get('formatted_address'),
            'rating': rating,
            'id': place_id,
            'foto_urls': foto_urls
        })
        seen_place_ids.add(place_id)

    # if not destinasi:
    #     flash("Tidak ditemukan hasil yang cocok.")
    #     return redirect(url_for('home'))

    return render_template('results.html', destinasi=destinasi, query=query)


@app.route('/wishlist')
def wishlist():
    if 'user_id' not in session:
        flash("Anda harus login untuk melihat wishlist.")
        return redirect(url_for('login'))

    cursor.execute(
        "SELECT * FROM wishlist WHERE user_id = %s",
        (session['user_id'],)
    )
    items = cursor.fetchall()

    return render_template('wishlist.html', items=items)

@app.route('/add_wishlist', methods=['POST'])
def add_wishlist():
    if 'user_id' not in session:
        flash("Anda harus login untuk menambahkan ke wishlist.")
        return redirect(url_for('login'))

    place_id = request.form['place_id']
    place_name = request.form['place_name']
    place_address = request.form['place_address']

    # Cek duplikat
    cursor.execute(
        "SELECT * FROM wishlist WHERE user_id = %s AND place_id = %s",
        (session['user_id'], place_id)
    )
    existing = cursor.fetchone()
    if existing:
        flash("Tempat sudah ada di wishlist.")
    else:
        cursor.execute(
            "INSERT INTO wishlist (user_id, place_id, place_name, place_address) VALUES (%s, %s, %s, %s)",
            (session['user_id'], place_id, place_name, place_address)
        )
        conn.commit()
        flash("Berhasil ditambahkan ke wishlist!")

    return redirect(url_for('wishlist'))



@app.route('/wishlist/delete/<int:wishlist_id>', methods=['POST'])
def delete_wishlist(wishlist_id):
    if 'user_id' not in session:
        flash("Anda harus login untuk menghapus dari wishlist.")
        return redirect(url_for('login'))

    cursor.execute(
        "DELETE FROM wishlist WHERE id = %s AND user_id = %s",
        (wishlist_id, session['user_id'])
    )
    conn.commit()
    flash("Wishlist berhasil dihapus.")
    return redirect(url_for('wishlist'))


@app.route('/random_place')
def random_place():
    # Ambil data random dari DB
    cursor.execute("SELECT * FROM wisata_random ORDER BY RAND() LIMIT 1")
    tempat = cursor.fetchone()

    if not tempat:
        flash("Belum ada data random wisata.")
        return redirect(url_for('home'))

    place_id = tempat['place_id']

    # Panggil detail Google
    detail_url = (
        f"https://maps.googleapis.com/maps/api/place/details/json"
        f"?place_id={place_id}&fields=name,rating,formatted_address,geometry,photos,types,opening_hours&key={GOOGLE_API_KEY}"
    )
    response = requests.get(detail_url).json()
    result = response.get('result', {})

    # --- Mapping kategori ---
    types = result.get('types', [])
    kategori_db = tempat.get('kategori')
    kategori_mapped = next(
        (type_descriptions[t] for t in types if t in type_descriptions),
        'Tempat'  # fallback jika tidak ketemu
    )
    kategori = kategori_db if kategori_db else kategori_mapped

    # --- Deskripsi: prioritas DB kalau ada ---
    deskripsi = tempat.get('deskripsi') if tempat.get('deskripsi') else kategori

    # --- Jam buka ---
    opening_hours = result.get('opening_hours', {})
    jam_buka = opening_hours.get('weekday_text', ["Buka setiap hari"])
    buka_sekarang = opening_hours.get('open_now')

    # --- Foto ---
    foto_urls = [
        get_photo_url(photo.get('photo_reference'))
        for photo in result.get('photos', [])
        if photo.get('photo_reference')
    ]

    destinasi = {
        'id': place_id,
        'nama': result.get('name'),
        'alamat': result.get('formatted_address'),
        'rating': result.get('rating'),
        'lokasi': result.get('geometry', {}).get('location'),
        'deskripsi': deskripsi,
        'kategori': kategori,
        'foto_urls': foto_urls,
        'jam_buka': jam_buka,
        'buka_sekarang': buka_sekarang
    }

    return render_template('detail.html', destinasi=destinasi)


# Run hanya sekali!
if __name__ == '__main__':
    app.run(debug=True)