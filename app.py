# -*- coding: utf-8 -*-
"""
Created on Mon Mar  2 19:41:34 2026

@author: U853765
"""

from flask import Flask, request, render_template, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
import json
import cloudinary
import cloudinary.uploader

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super_ultra_secret_key")  # cambiar en prod

# ---------------- CONFIGURACIÓN ----------------
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tortillas.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB

db = SQLAlchemy(app)

# ---------------- CLOUDINARY ----------------
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET')
)

# ---------------- MODELOS ----------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Tortilla(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    location = db.Column(db.String(200))  # lat,lng
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    price = db.Column(db.Float)
    photo = db.Column(db.String(300))  # ahora será la URL de Cloudinary
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    ratings = db.relationship('Rating', backref='tortilla', cascade="all, delete", lazy=True)
    likes = db.relationship('Like', backref='tortilla', cascade="all, delete", lazy=True)

    def average_score(self):
        if not self.ratings:
            return 0
        return round(sum(r.total_score() for r in self.ratings)/len(self.ratings), 2)

class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flavor = db.Column(db.Integer)
    texture = db.Column(db.Integer)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tortilla_id = db.Column(db.Integer, db.ForeignKey('tortilla.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User')

    def total_score(self):
        return round((self.flavor + self.texture)/2, 2)

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tortilla_id = db.Column(db.Integer, db.ForeignKey('tortilla.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

# ---------------- AUTH ----------------
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if not username or not password:
            flash("Rellena todos los campos")
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash("Ese usuario ya existe 😅")
            return redirect(url_for('register'))

        hashed = generate_password_hash(password)
        user = User(username=username, password=hashed)
        db.session.add(user)
        db.session.commit()
        flash("Usuario creado correctamente ✅")
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('home'))
        return render_template('login.html', error="Usuario o contraseña incorrectos")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')

        if not username or not password or not password_confirm:
            flash("Por favor rellena todos los campos", "error")
            return redirect(url_for('reset_password'))

        if len(password) < 6:
            flash("La contraseña debe tener al menos 6 caracteres", "error")
            return redirect(url_for('reset_password'))

        if password != password_confirm:
            flash("Las contraseñas no coinciden", "error")
            return redirect(url_for('reset_password'))

        user = User.query.filter_by(username=username).first()
        if not user:
            flash("No existe ningún usuario con ese nombre", "error")
            return redirect(url_for('reset_password'))

        try:
            user.password = generate_password_hash(password)
            db.session.commit()
            flash("Contraseña cambiada correctamente. Ya puedes iniciar sesión.", "success")
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash("Error al cambiar la contraseña", "error")
            return redirect(url_for('reset_password'))

    return render_template('reset_password.html')

# ---------------- HOME ----------------
@app.route('/', methods=['GET','POST'])
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        # ---------------- FOTO ----------------
        file = request.files.get('photo')
        if file and file.filename != '':
            upload_result = cloudinary.uploader.upload(file)
            filename = upload_result['secure_url']
        else:
            filename = None

        # ---------------- PRECIO ----------------
        try:
            price = float(request.form.get('price', 0))
            if price < 0:
                price = 0
        except ValueError:
            price = 0

        # ---------------- LAT/LNG ----------------
        lat_lng = request.form.get('location', '')
        latitude, longitude = None, None
        if lat_lng and ',' in lat_lng:
            try:
                latitude, longitude = map(float, lat_lng.split(','))
            except ValueError:
                latitude, longitude = None, None

        # ---------------- CREAR TORTILLA ----------------
        tortilla = Tortilla(
            name=request.form.get('name', '').strip(),
            location=lat_lng,
            latitude=latitude,
            longitude=longitude,
            price=price,
            photo=filename
        )
        db.session.add(tortilla)
        db.session.commit()

        # ---------------- CREAR RATING ----------------
        try:
            rating = Rating(
                flavor=int(request.form.get('flavor', 1)),
                texture=int(request.form.get('texture', 1)),
                comment=request.form.get('comment', '').strip(),
                tortilla_id=tortilla.id,
                user_id=session['user_id']
            )
            db.session.add(rating)
            db.session.commit()
        except ValueError:
            pass

        return redirect(url_for('home'))

    tortillas = Tortilla.query.order_by(Tortilla.created_at.desc()).all()
    return render_template('index.html', tortillas=tortillas, user_id=session['user_id'])

# ---------------- LIKE ----------------
@app.route('/like/<int:id>', methods=['POST'])
def like(id):
    if 'user_id' not in session:
        return jsonify({"error": "login required"}), 403
    existing = Like.query.filter_by(tortilla_id=id, user_id=session['user_id']).first()
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(Like(tortilla_id=id, user_id=session['user_id']))
    db.session.commit()
    total = Like.query.filter_by(tortilla_id=id).count()
    return jsonify({"likes": total})

# ---------------- PROFILE ----------------
@app.route('/profile/<int:id>')
def profile(id):
    user = User.query.get_or_404(id)
    ratings = Rating.query.filter_by(user_id=id).order_by(Rating.created_at.desc()).all()
    tortillas = [r.tortilla for r in ratings]
    total = len(tortillas)
    if total > 0:
        avg = round(sum(t.average_score() for t in tortillas)/total,2)
        best = max(tortillas, key=lambda t: t.average_score())
        likes = sum(len(t.likes) for t in tortillas)
    else:
        avg, best, likes = 0, None, 0
    return render_template("profile.html", user=user, total=total, avg=avg, best=best, likes=likes, ratings=ratings)

# ---------------- RANKING ----------------
@app.route('/ranking')
def ranking():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    tortillas = Tortilla.query.all()
    sorted_tortillas = sorted(tortillas, key=lambda t: t.average_score(), reverse=True)
    return render_template("ranking.html", tortillas=sorted_tortillas)

# ---------------- SELECT LOCATION ----------------
@app.route('/select_location')
def select_location():
    return render_template('select_location.html')

# ---------------- EXPORT BACKUP ----------------
@app.route('/admin/export')
def admin_export():
    backup_key = os.environ.get('BACKUP_KEY', 'tortillas2024')
    if request.args.get('key') != backup_key:
        return "No autorizado. Añade ?key=TU_BACKUP_KEY a la URL", 403

    data = {
        "users": [{"id": u.id, "username": u.username} for u in User.query.all()],
        "tortillas": [{"id": t.id, "name": t.name, "location": t.location,
                       "latitude": t.latitude, "longitude": t.longitude,
                       "price": t.price, "photo": t.photo,
                       "created_at": t.created_at.isoformat() if t.created_at else None}
                      for t in Tortilla.query.all()],
        "ratings": [{"id": r.id, "tortilla_id": r.tortilla_id, "user_id": r.user_id,
                     "flavor": r.flavor, "texture": r.texture, "comment": r.comment,
                     "created_at": r.created_at.isoformat() if r.created_at else None}
                    for r in Rating.query.all()],
        "likes": [{"id": l.id, "tortilla_id": l.tortilla_id, "user_id": l.user_id}
                  for l in Like.query.all()],
    }
    from flask import make_response
    response = make_response(json.dumps(data, ensure_ascii=False, indent=2))
    response.headers['Content-Type'] = 'application/json'
    response.headers['Content-Disposition'] = 'attachment; filename=tortillas_backup.json'
    return response

# ---------------- IMPORT BACKUP ----------------
@app.route('/admin/import', methods=['GET', 'POST'])
def admin_import():
    backup_key = os.environ.get('BACKUP_KEY', 'tortillas2024')
    if request.args.get('key') != backup_key:
        return "No autorizado. Añade ?key=TU_BACKUP_KEY a la URL", 403

    if request.method == 'POST':
        file = request.files.get('backup')
        if not file or not file.filename.endswith('.json'):
            return "Sube un archivo .json válido", 400

        try:
            data = json.loads(file.read().decode('utf-8'))
        except Exception:
            return "El archivo JSON no es válido", 400

        PLACEHOLDER_PASSWORD = generate_password_hash("cambiar_esta_contraseña_123")
        imported = {"usuarios": 0, "tortillas": 0, "ratings": 0, "likes": 0}

        for u in data.get("users", []):
            if not User.query.get(u["id"]):
                db.session.add(User(id=u["id"], username=u["username"], password=PLACEHOLDER_PASSWORD))
                imported["usuarios"] += 1

        db.session.flush()

        for t in data.get("tortillas", []):
            if not Tortilla.query.get(t["id"]):
                db.session.add(Tortilla(
                    id=t["id"], name=t.get("name", ""), location=t.get("location"),
                    latitude=t.get("latitude"), longitude=t.get("longitude"),
                    price=t.get("price", 0), photo=t.get("photo"),
                    created_at=datetime.fromisoformat(t["created_at"]) if t.get("created_at") else datetime.utcnow()
                ))
                imported["tortillas"] += 1

        db.session.flush()

        for r in data.get("ratings", []):
            if not Rating.query.get(r["id"]):
                db.session.add(Rating(
                    id=r["id"], tortilla_id=r["tortilla_id"], user_id=r["user_id"],
                    flavor=r["flavor"], texture=r["texture"], comment=r.get("comment"),
                    created_at=datetime.fromisoformat(r["created_at"]) if r.get("created_at") else datetime.utcnow()
                ))
                imported["ratings"] += 1

        for l in data.get("likes", []):
            if not Like.query.get(l["id"]):
                db.session.add(Like(id=l["id"], tortilla_id=l["tortilla_id"], user_id=l["user_id"]))
                imported["likes"] += 1

        db.session.commit()

        return f"""
        <h2>Importacion completada</h2>
        <ul>
            <li>Usuarios: {imported['usuarios']}</li>
            <li>Tortillas: {imported['tortillas']}</li>
            <li>Ratings: {imported['ratings']}</li>
            <li>Likes: {imported['likes']}</li>
        </ul>
        <p><b>Aviso:</b> Las contraseñas han sido reseteadas. Los usuarios deben ir a
        <a href="/reset-password">/reset-password</a> para crear una nueva.</p>
        <a href="/">Ir a la app</a>
        """

    return '''
    <h2>Importar backup JSON</h2>
    <form method="POST" enctype="multipart/form-data">
        <input type="file" name="backup" accept=".json" required>
        <button type="submit">Importar</button>
    </form>
    '''

# ---------------- INIT ----------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)