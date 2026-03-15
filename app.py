from flask import Flask, request, render_template, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import uuid
import logging
import json

# ============ CONFIGURACIÓN ============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, 'static', 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cloudinary (solo si están configuradas las variables de entorno)
CLOUDINARY_CONFIGURED = bool(os.environ.get('CLOUDINARY_CLOUD_NAME'))
if CLOUDINARY_CONFIGURED:
    import cloudinary
    import cloudinary.uploader
    cloudinary.config(
        cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
        api_key=os.environ.get('CLOUDINARY_API_KEY'),
        api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
        secure=True
    )
    logger.info("Cloudinary configurado correctamente")

# Inicialización de Flask
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super_ultra_secret_key")
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Configuración de la base de datos
# Railway usa postgres://, SQLAlchemy necesita postgresql://
_db_url = os.environ.get('DATABASE_URL', 'sqlite:///tortillas.db')
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB
app.config['UPLOAD_FOLDER'] = UPLOAD_DIR
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

db = SQLAlchemy(app)

# ============ UTILIDADES ============
def allowed_file(filename):
    """Valida si la extensión del archivo es permitida"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def validate_rating_score(score):
    """Valida que la puntuación esté entre 0.5 y 5"""
    try:
        score = float(score)
        return max(0.5, min(5, score))
    except (ValueError, TypeError):
        return 0.5

def validate_price(price):
    """Valida que el precio sea positivo"""
    try:
        price = float(price)
        return max(0, price)
    except (ValueError, TypeError):
        return 0

# ============ MODELOS ============
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False, index=True)
    password = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<User {self.username}>'

class Tortilla(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    name_normalized = db.Column(db.String(100), index=True, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='created_tortillas')
    location = db.Column(db.String(200))
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    price = db.Column(db.Float, default=0)
    photo = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    ratings = db.relationship('Rating', backref='tortilla', cascade="all, delete", lazy=True)
    likes = db.relationship('Like', backref='tortilla', cascade="all, delete", lazy=True)

    def average_score(self):
        """Calcula la puntuación promedio de la tortilla"""
        if not self.ratings:
            return 0
        return round(sum(r.total_score() for r in self.ratings) / len(self.ratings), 2)

    def __repr__(self):
        return f'<Tortilla {self.name}>'

class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flavor = db.Column(db.Float, nullable=False)
    texture = db.Column(db.Float, nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    tortilla_id = db.Column(db.Integer, db.ForeignKey('tortilla.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User')

    def total_score(self):
        """Calcula el promedio entre sabor y textura"""
        return round((self.flavor + self.texture) / 2, 2)

    def __repr__(self):
        return f'<Rating {self.id}>'

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tortilla_id = db.Column(db.Integer, db.ForeignKey('tortilla.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('tortilla_id', 'user_id', name='unique_user_tortilla_like'),)

    def __repr__(self):
        return f'<Like {self.id}>'

# ============ AUTENTICACIÓN ============
@app.route('/register', methods=['GET', 'POST'])
def register():
    """Ruta para registrar nuevos usuarios"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')

        # Validación
        if not username or not password:
            flash("Por favor rellena todos los campos", "error")
            return redirect(url_for('register'))

        if len(username) < 3:
            flash("El usuario debe tener al menos 3 caracteres", "error")
            return redirect(url_for('register'))

        if len(password) < 6:
            flash("La contraseña debe tener al menos 6 caracteres", "error")
            return redirect(url_for('register'))

        if password != password_confirm:
            flash("Las contraseñas no coinciden", "error")
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash("Ese usuario ya existe 😅", "warning")
            return redirect(url_for('register'))

        try:
            hashed_password = generate_password_hash(password)
            user = User(username=username, password=hashed_password)
            db.session.add(user)
            db.session.commit()
            flash("Usuario creado correctamente ✅", "success")
            logger.info(f"Nuevo usuario registrado: {username}")
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error al registrar usuario: {e}")
            flash("Error al registrar el usuario", "error")
            return redirect(url_for('register'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Ruta para iniciar sesión"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            logger.info(f"Usuario {username} inició sesión")
            return redirect(url_for('home'))
        
        flash("Usuario o contraseña incorrectos", "error")
        logger.warning(f"Intento de login fallido para usuario: {username}")

    return render_template('login.html')

@app.route('/logout')
def logout():
    """Ruta para cerrar sesión"""
    username = session.get('username', 'Unknown')
    session.clear()
    logger.info(f"Usuario {username} cerró sesión")
    return redirect(url_for('login'))

# ============ HOME ============
@app.route('/', methods=['GET', 'POST'])
def home():
    """Ruta principal - mostrar tortillas y crear nuevas"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            # Procesamiento de archivo
            filename = None
            file = request.files.get('photo')
            if file and file.filename != '' and allowed_file(file.filename):
                if CLOUDINARY_CONFIGURED:
                    result = cloudinary.uploader.upload(
                        file,
                        folder='tortillapp',
                        transformation=[{'width': 1000, 'crop': 'limit', 'quality': 'auto', 'fetch_format': 'auto'}]
                    )
                    filename = result['secure_url']
                    logger.info(f"Imagen subida a Cloudinary: {filename}")
                else:
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    filename = f"{uuid.uuid4()}.{ext}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    logger.info(f"Archivo guardado localmente: {filename}")

            # Validación de datos
            name = request.form.get('name', '').strip()
            if not name:
                flash("El nombre de la tortilla es requerido", "error")
                return redirect(url_for('home'))

            price = validate_price(request.form.get('price', 0))
            location = request.form.get('location', '').strip() or None
            try:
                latitude = float(request.form.get('latitude')) if request.form.get('latitude') else None
                longitude = float(request.form.get('longitude')) if request.form.get('longitude') else None
            except (ValueError, TypeError):
                latitude = longitude = None

            # Comprobar duplicados por nombre para el mismo usuario
            existing_name = Tortilla.query.filter_by(
                name_normalized=name.lower(),
                created_by=session['user_id']
            ).first()
            if existing_name:
                flash(f"Ya tienes una tortilla llamada '{name}' registrada", "warning")
                return redirect(url_for('home'))

            # Comprobar duplicados por ubicación para el mismo usuario (si se indicó)
            if location:
                existing_location = Tortilla.query.filter(
                    Tortilla.created_by == session['user_id'],
                    db.func.lower(Tortilla.location) == location.lower()
                ).first()
                if existing_location:
                    flash(f"Ya tienes una tortilla registrada en esa ubicación ('{existing_location.name}')", "warning")
                    return redirect(url_for('home'))

            sabor = validate_rating_score(request.form.get('sabor', 0.5))
            textura = validate_rating_score(request.form.get('textura', 0.5))
            comment = request.form.get('comment', '').strip()

            # Crear tortilla
            tortilla = Tortilla(
                name=name,
                name_normalized=name.lower(),
                location=location,
                latitude=latitude,
                longitude=longitude,
                price=price,
                photo=filename,
                created_by=session['user_id']
            )
            db.session.add(tortilla)
            db.session.flush()

            # Crear rating
            rating = Rating(
                flavor=sabor,
                texture=textura,
                comment=comment,
                tortilla_id=tortilla.id,
                user_id=session['user_id']
            )
            db.session.add(rating)
            db.session.commit()

            flash(f"¡Tortilla '{name}' creada correctamente! 🎉", "success")
            logger.info(f"Tortilla creada: {name} por usuario {session['user_id']}")
            return redirect(url_for('home'))

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error al crear tortilla: {e}")
            flash("Error al crear la tortilla", "error")
            return redirect(url_for('home'))

    # Agrupar tortillas por nombre y recoger todas las fotos de cada una
    all_tortillas = Tortilla.query.order_by(Tortilla.created_at.desc()).all()

    name_photos = {}   # name_normalized -> lista de fotos
    name_stats = {}    # name_normalized -> {'count': N, 'avg': X}
    for t in all_tortillas:
        key = t.name_normalized
        if key not in name_photos:
            name_photos[key] = []
            name_stats[key] = {'total': 0.0, 'count': 0}
        if t.photo:
            name_photos[key].append(t.photo)
        for r in t.ratings:
            name_stats[key]['total'] += r.total_score()
            name_stats[key]['count'] += 1

    # Calcular medias
    for key, s in name_stats.items():
        s['avg'] = round(s['total'] / s['count'], 2) if s['count'] > 0 else 0

    # Una card por nombre único (la más reciente primero)
    seen = set()
    tortillas = []
    for t in all_tortillas:
        if t.name_normalized not in seen:
            seen.add(t.name_normalized)
            tortillas.append(t)

    return render_template('index.html', tortillas=tortillas, name_photos=name_photos, name_stats=name_stats)

# ============ LIKES ============
@app.route('/like/<int:tortilla_id>', methods=['POST'])
def like(tortilla_id):
    """Ruta para dar/quitar like a una tortilla"""
    if 'user_id' not in session:
        return jsonify({"error": "Login requerido"}), 403

    try:
        tortilla = Tortilla.query.get_or_404(tortilla_id)
        user_id = session['user_id']

        existing_like = Like.query.filter_by(
            tortilla_id=tortilla_id,
            user_id=user_id
        ).first()

        if existing_like:
            db.session.delete(existing_like)
            liked = False
        else:
            new_like = Like(tortilla_id=tortilla_id, user_id=user_id)
            db.session.add(new_like)
            liked = True

        db.session.commit()
        total_likes = Like.query.filter_by(tortilla_id=tortilla_id).count()

        logger.info(f"Like {'añadido' if liked else 'removido'} a tortilla {tortilla_id}")
        return jsonify({"likes": total_likes, "liked": liked})

    except Exception as e:
        logger.error(f"Error al procesar like: {e}")
        return jsonify({"error": "Error al procesar el like"}), 500

# ============ PERFIL ============
@app.route('/profile/<int:user_id>')
def profile(user_id):
    """Mostrar perfil del usuario"""
    user = User.query.get_or_404(user_id)
    ratings = Rating.query.filter_by(user_id=user_id).order_by(Rating.created_at.desc()).all()
    tortillas = [r.tortilla for r in ratings]

    total = len(tortillas)
    avg = round(sum(t.average_score() for t in tortillas) / total, 2) if total > 0 else 0
    best = max(tortillas, key=lambda t: t.average_score()) if total > 0 else None
    likes = sum(len(t.likes) for t in tortillas)

    logger.info(f"Perfil visitado: {user.username}")
    return render_template("profile.html", user=user, total=total, avg=avg, best=best, likes=likes, ratings=ratings)

# ============ RANKING ============
@app.route('/ranking')
def ranking():
    """Mostrar top 10 de tortillas mejor valoradas"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    tortillas = Tortilla.query.all()
    sorted_tortillas = sorted(
        tortillas,
        key=lambda t: t.average_score(),
        reverse=True
    )[:10]

    map_data = json.dumps([
        {
            'name': t.name,
            'score': t.average_score(),
            'location': t.location,
            'lat': t.latitude,
            'lng': t.longitude,
            'rank': i + 1,
        }
        for i, t in enumerate(sorted_tortillas)
        if t.location  # incluir aunque no tengan coords aún
    ])

    logger.info("Ranking consultado")
    return render_template("ranking.html", tortillas=sorted_tortillas, map_data=map_data)

# ============ SELECCIONAR UBICACIÓN ============
@app.route('/select_location')
def select_location():
    """Página para seleccionar ubicación con buscador"""
    return render_template('select_location.html')

# ============ MANEJO DE ERRORES ============
@app.errorhandler(404)
def page_not_found(error):
    """Manejo de error 404"""
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    """Manejo de error 500"""
    logger.error(f"Error interno del servidor: {error}")
    return render_template('500.html'), 500

# ============ INICIALIZACIÓN ============
def init_db():
    """Crea tablas y aplica migraciones compatibles con SQLite y PostgreSQL"""
    db.create_all()
    if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
        from sqlalchemy import text
        with db.engine.connect() as conn:
            for col in ['latitude FLOAT', 'longitude FLOAT']:
                try:
                    conn.execute(text(f'ALTER TABLE tortilla ADD COLUMN {col}'))
                    conn.commit()
                except Exception:
                    pass  # La columna ya existe

with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG', False))