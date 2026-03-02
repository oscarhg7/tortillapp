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

# ---------------- INIT ----------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)