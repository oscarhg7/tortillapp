from flask import Flask, request, render_template, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import uuid
import logging
import json
import re

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
_STOP_WORDS = {'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas',
               'de', 'del', 'con', 'a', 'en', 'y', 'e', 'o', 'u', 'al'}

def normalize_name(name):
    """Elimina artículos y preposiciones para comparar nombres de tortillas."""
    words = re.split(r'\s+', name.lower().strip())
    filtered = [w for w in words if w and w not in _STOP_WORDS]
    return ' '.join(filtered) if filtered else name.lower().strip()

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
    email = db.Column(db.String(255), unique=True, nullable=False)
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

class Reply(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rating_id = db.Column(db.Integer, db.ForeignKey('rating.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User')
    rating = db.relationship('Rating', backref='replies')

    def __repr__(self):
        return f'<Reply {self.id}>'

# ============ AUTENTICACIÓN ============
@app.route('/register', methods=['GET', 'POST'])
def register():
    """Ruta para registrar nuevos usuarios"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')

        # Validación
        if not username or not password or not email:
            flash("Por favor rellena todos los campos", "error")
            return redirect(url_for('register'))

        if len(username) < 3:
            flash("El usuario debe tener al menos 3 caracteres", "error")
            return redirect(url_for('register'))

        if '@' not in email or '.' not in email.split('@')[-1]:
            flash("Introduce un email válido", "error")
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

        if User.query.filter_by(email=email).first():
            flash("Ese email ya está registrado", "warning")
            return redirect(url_for('register'))

        try:
            hashed_password = generate_password_hash(password)
            user = User(username=username, email=email, password=hashed_password)
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
            logger.error(f"Error al cambiar contraseña: {e}")
            flash("Error al cambiar la contraseña", "error")
            return redirect(url_for('reset_password'))

    return render_template('reset_password.html')

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
                name_normalized=normalize_name(name),
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
                name_normalized=normalize_name(name),
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

    current_user_id = session['user_id']
    name_photos = {}   # name_normalized -> lista de fotos
    name_stats = {}    # name_normalized -> dict con medias y primer usuario
    for t in all_tortillas:
        key = t.name_normalized
        if key not in name_photos:
            name_photos[key] = []
            name_stats[key] = {
                'flavor_total': 0.0,
                'texture_total': 0.0,
                'count': 0,
                'last_price': 0,
                'display_name': t.name,
                'first_user': t.user.username,
                'total_likes': 0,
                'user_liked': False,
                'user_tortilla_id': None,
                'comment_count': 0,
            }
        else:
            # all_tortillas está ordenado desc, así que el último visto es el más antiguo
            name_stats[key]['first_user'] = t.user.username
        # Nombre más largo como nombre representativo
        if len(t.name) > len(name_stats[key]['display_name']):
            name_stats[key]['display_name'] = t.name
        # Guardar el precio más reciente que no sea 0
        if t.price and name_stats[key]['last_price'] == 0:
            name_stats[key]['last_price'] = t.price
        if t.photo:
            name_photos[key].append(t.photo)
        for r in t.ratings:
            name_stats[key]['flavor_total'] += r.flavor
            name_stats[key]['texture_total'] += r.texture
            name_stats[key]['count'] += 1
            if r.comment:
                name_stats[key]['comment_count'] += 1
        # Acumular likes del grupo
        name_stats[key]['total_likes'] += len(t.likes)
        if not name_stats[key]['user_liked']:
            name_stats[key]['user_liked'] = any(l.user_id == current_user_id for l in t.likes)
        # Tortilla del usuario actual en este grupo
        if t.created_by == current_user_id:
            name_stats[key]['user_tortilla_id'] = t.id

    # Calcular medias
    for key, s in name_stats.items():
        if s['count'] > 0:
            s['avg_flavor']  = round(s['flavor_total']  / s['count'], 1)
            s['avg_texture'] = round(s['texture_total'] / s['count'], 1)
            s['avg'] = round((s['flavor_total'] + s['texture_total']) / (2 * s['count']), 2)
        else:
            s['avg_flavor'] = s['avg_texture'] = s['avg'] = 0

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
        # Total de likes del grupo (mismo nombre normalizado)
        sibling_ids = [t.id for t in Tortilla.query.filter_by(name_normalized=tortilla.name_normalized).all()]
        total_likes = Like.query.filter(Like.tortilla_id.in_(sibling_ids)).count()

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
    """Mostrar top 10 de tortillas mejor valoradas, agrupadas por nombre"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    all_tortillas = Tortilla.query.order_by(Tortilla.created_at.desc()).all()

    # Agrupar por nombre normalizado (igual que en home)
    groups = {}
    for t in all_tortillas:
        key = t.name_normalized
        if key not in groups:
            groups[key] = {
                'id': t.id,
                'name': t.name,
                'name_normalized': key,
                'photos': [],
                'flavor_total': 0.0,
                'texture_total': 0.0,
                'count': 0,
                'likes': 0,
                'first_user': t.user.username,
                'first_date': t.created_at,
                'location': t.location,
                'lat': t.latitude,
                'lng': t.longitude,
                'price': t.price if t.price else 0,
            }
        else:
            # Iteramos de más reciente a más antiguo: el último es el primero publicado
            groups[key]['first_user'] = t.user.username
            groups[key]['first_date'] = t.created_at
            # Tomar coords/ubicación del primero que las tenga
            if not groups[key]['lat'] and t.latitude:
                groups[key]['lat'] = t.latitude
                groups[key]['lng'] = t.longitude
            if not groups[key]['location'] and t.location:
                groups[key]['location'] = t.location
            # Precio más reciente no-cero
            if t.price and groups[key]['price'] == 0:
                groups[key]['price'] = t.price
        # Nombre más largo como nombre representativo
        if len(t.name) > len(groups[key]['name']):
            groups[key]['name'] = t.name

        if t.photo:
            groups[key]['photos'].append(t.photo)
        for r in t.ratings:
            groups[key]['flavor_total'] += r.flavor
            groups[key]['texture_total'] += r.texture
            groups[key]['count'] += 1
        groups[key]['likes'] += len(t.likes)

    # Calcular medias por grupo
    for g in groups.values():
        if g['count'] > 0:
            g['avg_flavor']  = round(g['flavor_total']  / g['count'], 1)
            g['avg_texture'] = round(g['texture_total'] / g['count'], 1)
            g['avg'] = round((g['flavor_total'] + g['texture_total']) / (2 * g['count']), 2)
        else:
            g['avg_flavor'] = g['avg_texture'] = g['avg'] = 0

    # Top 10 por media
    ranking_list = sorted(groups.values(), key=lambda g: g['avg'], reverse=True)[:10]

    map_data = json.dumps([
        {
            'name': g['name'],
            'score': g['avg'],
            'location': g['location'],
            'lat': g['lat'],
            'lng': g['lng'],
            'rank': i + 1,
        }
        for i, g in enumerate(ranking_list)
        if g['location']
    ])

    logger.info("Ranking consultado")
    return render_template("ranking.html", tortillas=ranking_list, map_data=map_data)

# ============ EDITAR TORTILLA ============
@app.route('/edit/<int:tortilla_id>', methods=['GET', 'POST'])
def edit_tortilla(tortilla_id):
    """Permite al usuario editar su propia tortilla y valoración"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    tortilla = Tortilla.query.get_or_404(tortilla_id)

    if tortilla.created_by != session['user_id']:
        flash("No puedes editar una tortilla que no es tuya", "error")
        return redirect(url_for('home'))

    rating = Rating.query.filter_by(tortilla_id=tortilla_id, user_id=session['user_id']).first()

    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            if not name:
                flash("El nombre es obligatorio", "error")
                return redirect(url_for('edit_tortilla', tortilla_id=tortilla_id))

            new_normalized = normalize_name(name)
            if new_normalized != tortilla.name_normalized:
                collision = Tortilla.query.filter_by(name_normalized=new_normalized, created_by=session['user_id']).first()
                if collision and collision.id != tortilla_id:
                    flash("Ya tienes otra tortilla con ese nombre registrada", "warning")
                    return redirect(url_for('edit_tortilla', tortilla_id=tortilla_id))

            file = request.files.get('photo')
            if file and file.filename != '' and allowed_file(file.filename):
                if CLOUDINARY_CONFIGURED:
                    result = cloudinary.uploader.upload(
                        file,
                        folder='tortillapp',
                        transformation=[{'width': 1000, 'crop': 'limit', 'quality': 'auto', 'fetch_format': 'auto'}]
                    )
                    tortilla.photo = result['secure_url']
                else:
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    filename = f"{uuid.uuid4()}.{ext}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    tortilla.photo = filename

            tortilla.name = name
            tortilla.name_normalized = new_normalized
            tortilla.price = validate_price(request.form.get('price', 0))
            date_str = request.form.get('created_at', '').strip()
            if date_str:
                try:
                    tortilla.created_at = datetime.strptime(date_str, '%Y-%m-%d')
                except ValueError:
                    pass
            tortilla.location = request.form.get('location', '').strip() or None
            try:
                tortilla.latitude = float(request.form.get('latitude')) if request.form.get('latitude') else None
                tortilla.longitude = float(request.form.get('longitude')) if request.form.get('longitude') else None
            except (ValueError, TypeError):
                tortilla.latitude = tortilla.longitude = None

            if rating:
                rating.flavor = validate_rating_score(request.form.get('sabor', 0.5))
                rating.texture = validate_rating_score(request.form.get('textura', 0.5))
                rating.comment = request.form.get('comment', '').strip()
            else:
                rating = Rating(
                    flavor=validate_rating_score(request.form.get('sabor', 0.5)),
                    texture=validate_rating_score(request.form.get('textura', 0.5)),
                    comment=request.form.get('comment', '').strip(),
                    tortilla_id=tortilla_id,
                    user_id=session['user_id']
                )
                db.session.add(rating)

            db.session.commit()
            flash(f"Tortilla '{name}' actualizada correctamente ✅", "success")
            logger.info(f"Tortilla {tortilla_id} editada por usuario {session['user_id']}")
            return redirect(url_for('home'))

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error al editar tortilla {tortilla_id}: {e}")
            flash("Error al guardar los cambios", "error")
            return redirect(url_for('edit_tortilla', tortilla_id=tortilla_id))

    return render_template('edit.html', tortilla=tortilla, rating=rating)


# ============ COMENTARIOS ============
@app.route('/comments/<int:tortilla_id>')
def comments(tortilla_id):
    """Muestra todos los comentarios del grupo al que pertenece la tortilla"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    ref = Tortilla.query.get_or_404(tortilla_id)
    siblings = Tortilla.query.filter_by(name_normalized=ref.name_normalized).all()
    sibling_ids = [t.id for t in siblings]

    ratings = (Rating.query
               .filter(Rating.tortilla_id.in_(sibling_ids))
               .order_by(Rating.created_at.desc())
               .all())

    display_name = max((t.name for t in siblings), key=len)

    return render_template('comments.html', display_name=display_name, ratings=ratings, ref_id=tortilla_id)


@app.route('/reply/<int:rating_id>', methods=['POST'])
def reply(rating_id):
    """Añade una respuesta a un rating"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    rating = Rating.query.get_or_404(rating_id)
    body = request.form.get('body', '').strip()

    if not body:
        flash("La respuesta no puede estar vacía", "error")
    elif len(body) > 500:
        flash("La respuesta no puede superar los 500 caracteres", "error")
    else:
        try:
            rep = Reply(rating_id=rating_id, user_id=session['user_id'], body=body)
            db.session.add(rep)
            db.session.commit()
            flash("Respuesta publicada ✅", "success")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error al guardar reply: {e}")
            flash("Error al publicar la respuesta", "error")

    return redirect(url_for('comments', tortilla_id=rating.tortilla_id))


# ============ EXPORTAR BASE DE DATOS (TEMPORAL) ============
@app.route('/admin/export')
def admin_export():
    """Exporta toda la base de datos como JSON. Protegido por BACKUP_KEY."""
    backup_key = os.environ.get('BACKUP_KEY', 'tortillas2024')
    if request.args.get('key') != backup_key:
        return "No autorizado. Añade ?key=TU_BACKUP_KEY a la URL", 403

    data = {
        'users': [
            {'id': u.id, 'username': u.username, 'email': u.email,
             'created_at': u.created_at.isoformat()}
            for u in User.query.all()
        ],
        'tortillas': [
            {'id': t.id, 'name': t.name, 'name_normalized': t.name_normalized,
             'created_by': t.created_by, 'location': t.location,
             'latitude': t.latitude, 'longitude': t.longitude,
             'price': t.price, 'photo': t.photo,
             'created_at': t.created_at.isoformat()}
            for t in Tortilla.query.all()
        ],
        'ratings': [
            {'id': r.id, 'tortilla_id': r.tortilla_id, 'user_id': r.user_id,
             'flavor': r.flavor, 'texture': r.texture, 'comment': r.comment,
             'created_at': r.created_at.isoformat()}
            for r in Rating.query.all()
        ],
        'likes': [
            {'id': l.id, 'tortilla_id': l.tortilla_id, 'user_id': l.user_id,
             'created_at': l.created_at.isoformat()}
            for l in Like.query.all()
        ],
        'replies': [
            {'id': r.id, 'rating_id': r.rating_id, 'user_id': r.user_id,
             'body': r.body, 'created_at': r.created_at.isoformat()}
            for r in Reply.query.all()
        ],
    }

    from flask import Response
    import json as _json
    return Response(
        _json.dumps(data, ensure_ascii=False, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment; filename=tortillas_backup.json'}
    )


# ============ IMPORTAR BACKUP ============
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
        imported = {"usuarios": 0, "tortillas": 0, "ratings": 0, "likes": 0, "replies": 0}

        for u in data.get("users", []):
            if not User.query.get(u["id"]):
                db.session.add(User(
                    id=u["id"], username=u["username"], email=u.get("email", f"{u['username']}@migrado.local"),
                    password=PLACEHOLDER_PASSWORD,
                    created_at=datetime.fromisoformat(u["created_at"]) if u.get("created_at") else datetime.utcnow()
                ))
                imported["usuarios"] += 1
        db.session.flush()

        for t in data.get("tortillas", []):
            if not Tortilla.query.get(t["id"]):
                db.session.add(Tortilla(
                    id=t["id"], name=t["name"],
                    name_normalized=t.get("name_normalized", t["name"].lower()),
                    created_by=t["created_by"], location=t.get("location"),
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
                db.session.add(Like(
                    id=l["id"], tortilla_id=l["tortilla_id"], user_id=l["user_id"],
                    created_at=datetime.fromisoformat(l["created_at"]) if l.get("created_at") else datetime.utcnow()
                ))
                imported["likes"] += 1

        for r in data.get("replies", []):
            if not Reply.query.get(r["id"]):
                db.session.add(Reply(
                    id=r["id"], rating_id=r["rating_id"], user_id=r["user_id"],
                    body=r["body"],
                    created_at=datetime.fromisoformat(r["created_at"]) if r.get("created_at") else datetime.utcnow()
                ))
                imported["replies"] += 1

        db.session.commit()
        return f"""
        <h2>Importacion completada</h2>
        <ul>
            <li>Usuarios: {imported['usuarios']}</li>
            <li>Tortillas: {imported['tortillas']}</li>
            <li>Ratings: {imported['ratings']}</li>
            <li>Likes: {imported['likes']}</li>
            <li>Replies: {imported['replies']}</li>
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

# ============ DIAGNÓSTICO (TEMPORAL) ============
@app.route('/admin/status')
def admin_status():
    """Comprueba que la app y la BD funcionan."""
    backup_key = os.environ.get('BACKUP_KEY', 'tortillas2024')
    if request.args.get('key') != backup_key:
        return "No autorizado", 403
    try:
        user_count = User.query.count()
        tortilla_count = Tortilla.query.count()
        rating_count = Rating.query.count()
        db_url = app.config['SQLALCHEMY_DATABASE_URI']
        db_type = 'postgresql' if 'postgresql' in db_url else 'sqlite'
        return jsonify({
            'status': 'ok',
            'db_type': db_type,
            'users': user_count,
            'tortillas': tortilla_count,
            'ratings': rating_count,
        })
    except Exception as e:
        return jsonify({'status': 'error', 'detail': str(e)}), 500


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
            try:
                conn.execute(text("ALTER TABLE user ADD COLUMN email VARCHAR(255) NOT NULL DEFAULT ''"))
                conn.commit()
            except Exception:
                pass  # La columna ya existe

with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG', False))