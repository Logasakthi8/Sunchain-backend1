import os
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import jwt
from werkzeug.utils import secure_filename
from functools import wraps
from bson import ObjectId
import json
import traceback

load_dotenv()

app = Flask(__name__)
CORS(app, origins=['https://sunchain-66av.onrender.com'], supports_credentials=True)

# MongoDB setup - Import models after app initialization
from models import mongo, User, Post
app.config['MONGO_URI'] = os.getenv('MONGODB_URI')
mongo.init_app(app)

app.config['SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-this')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        try:
            token = token.split(' ')[1]
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = User.find_by_id(data['user_id'])
            if not current_user:
                return jsonify({'message': 'User not found!'}), 401
        except Exception as e:
            print(f"Token error: {e}")
            return jsonify({'message': 'Token is invalid!'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

@app.route('/api/signup', methods=['POST'])
def signup():
    try:
        data = request.get_json()
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        
        if not username or not email or not password:
            return jsonify({'message': 'Missing fields'}), 400
        
        existing_user = User.find_by_email(email)
        if existing_user:
            return jsonify({'message': 'User already exists'}), 400
        
        result = User.create_user(username, email, password)
        token = jwt.encode({
            'user_id': str(result.inserted_id),
            'exp': datetime.utcnow() + timedelta(days=7)
        }, app.config['SECRET_KEY'], algorithm='HS256')
        
        return jsonify({
            'token': token,
            'user': {
                '_id': str(result.inserted_id),
                'username': username,
                'email': email,
                'points': 0,
                'total_blogs': 0
            }
        })
    except Exception as e:
        print(f"Signup error: {e}")
        traceback.print_exc()
        return jsonify({'message': str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        
        user = User.find_by_email(email)
        if not user or not User.verify_password(user, password):
            return jsonify({'message': 'Invalid credentials'}), 401
        
        token = jwt.encode({
            'user_id': str(user['_id']),
            'exp': datetime.utcnow() + timedelta(days=7)
        }, app.config['SECRET_KEY'], algorithm='HS256')
        
        return jsonify({
            'token': token,
            'user': {
                '_id': str(user['_id']),
                'username': user['username'],
                'email': user['email'],
                'points': user.get('points', 0),
                'total_blogs': user.get('total_blogs', 0)
            }
        })
    except Exception as e:
        print(f"Login error: {e}")
        traceback.print_exc()
        return jsonify({'message': str(e)}), 500

@app.route('/api/posts', methods=['GET'])
def get_posts():
    try:
        posts = Post.get_all_posts(20)
        return jsonify(posts)
    except Exception as e:
        print(f"Error fetching posts: {e}")
        traceback.print_exc()
        return jsonify([]), 200

@app.route('/api/posts/<post_id>', methods=['GET'])
def get_post(post_id):
    try:
        post = Post.get_post_by_id(post_id)
        if not post:
            return jsonify({'message': 'Post not found'}), 404
        return jsonify(post)
    except Exception as e:
        print(f"Error fetching post: {e}")
        traceback.print_exc()
        return jsonify({'message': str(e)}), 500

@app.route('/api/posts', methods=['POST'])
@token_required
def create_post(current_user):
    try:
        print("=" * 50)
        print("CREATE POST REQUEST")
        
        title = request.form.get('title')
        category = request.form.get('category')
        content = request.form.get('content')
        image = request.files.get('image')
        
        print(f"Title: {title}")
        print(f"Category: {category}")
        print(f"Content length: {len(content) if content else 0}")
        print(f"Image: {image.filename if image else 'No image'}")
        
        if not title:
            return jsonify({'message': 'Title is required'}), 400
        
        if not content:
            return jsonify({'message': 'Content is required'}), 400
        
        image_data = None
        image_filename = None
        
        if image and allowed_file(image.filename):
            image_data = image.read()
            image_filename = secure_filename(image.filename)
            print(f"Image size: {len(image_data)} bytes")
        
        result = Post.create_post(
            title=title,
            category=category,
            content=content,
            image_data=image_data,
            image_filename=image_filename,
            author_id=current_user['_id'],
            author_name=current_user['username']
        )
        
        User.update_points(current_user['_id'], 200)
        
        print(f"Post created successfully: {result.inserted_id}")
        print("=" * 50)
        
        return jsonify({
            'message': 'Post created',
            'post_id': str(result.inserted_id),
            'points_earned': 200
        })
    except Exception as e:
        print(f"Error creating post: {e}")
        traceback.print_exc()
        return jsonify({'message': str(e)}), 500

@app.route('/api/posts/<post_id>/like', methods=['POST'])
@token_required
def like_post(current_user, post_id):
    try:
        Post.like_post(post_id)
        return jsonify({'message': 'Post liked'})
    except Exception as e:
        print(f"Error liking post: {e}")
        return jsonify({'message': str(e)}), 500

@app.route('/api/posts/<post_id>/comment', methods=['POST'])
@token_required
def add_comment(current_user, post_id):
    try:
        data = request.get_json()
        comment = {
            'user_id': str(current_user['_id']),
            'username': current_user['username'],
            'text': data.get('text'),
            'created_at': datetime.utcnow().isoformat()
        }
        Post.add_comment(post_id, comment)
        return jsonify({'message': 'Comment added'})
    except Exception as e:
        print(f"Error adding comment: {e}")
        return jsonify({'message': str(e)}), 500

@app.route('/api/user/posts', methods=['GET'])
@token_required
def get_user_posts(current_user):
    try:
        posts = Post.get_posts_by_user(current_user['_id'])
        return jsonify(posts)
    except Exception as e:
        print(f"Error fetching user posts: {e}")
        return jsonify([]), 200

@app.route('/api/user/profile', methods=['GET'])
@token_required
def get_profile(current_user):
    try:
        return jsonify({
            '_id': str(current_user['_id']),
            'username': current_user['username'],
            'email': current_user['email'],
            'points': current_user.get('points', 0),
            'total_blogs': current_user.get('total_blogs', 0)
        })
    except Exception as e:
        print(f"Error fetching profile: {e}")
        return jsonify({'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
