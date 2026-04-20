import os
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import jwt
from werkzeug.utils import secure_filename
from functools import wraps
from bson import ObjectId, Binary
import json
import traceback
import bcrypt
import base64

load_dotenv()

app = Flask(__name__)
CORS(app, origins=['https://sunchain-66av.onrender.com'], supports_credentials=True)

# MongoDB setup - Initialize PyMongo
from flask_pymongo import PyMongo
app.config['MONGO_URI'] = os.getenv('MONGODB_URI')
mongo = PyMongo(app)

app.config['SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-this')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

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
            current_user = mongo.db.users.find_one({'_id': ObjectId(data['user_id'])})
            if not current_user:
                return jsonify({'message': 'User not found!'}), 401
        except Exception as e:
            print(f"Token error: {e}")
            return jsonify({'message': 'Token is invalid!'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

# ==================== AUTH ROUTES ====================

@app.route('/api/signup', methods=['POST'])
def signup():
    try:
        data = request.get_json()
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        
        if not username or not email or not password:
            return jsonify({'message': 'Missing fields'}), 400
        
        existing_user = mongo.db.users.find_one({'email': email})
        if existing_user:
            return jsonify({'message': 'User already exists'}), 400
        
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
        user = {
            'username': username,
            'email': email,
            'password': hashed,
            'points': 0,
            'total_posts': 0,
            'subscribers': [],
            'subscribed_channels': [],
            'created_at': datetime.utcnow()
        }
        result = mongo.db.users.insert_one(user)
        
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
                'total_posts': 0
            }
        })
    except Exception as e:
        print(f"Signup error: {e}")
        traceback.print_exc()
        return jsonify({'message': str(e)}), 500

@app.route('/api/user/subscriptions', methods=['GET'])
@token_required
def get_user_subscriptions(current_user):
    try:
        user = mongo.db.users.find_one({'_id': current_user['_id']})
        subscribed_channel_ids = user.get('subscribed_channels', [])
        
        channels = []
        for channel_id in subscribed_channel_ids:
            channel = mongo.db.channels.find_one({'_id': ObjectId(channel_id)})
            if channel:
                channel_dict = {
                    '_id': str(channel['_id']),
                    'name': channel['name'],
                    'description': channel.get('description', ''),
                    'subscriber_count': channel.get('subscriber_count', 0),
                    'owner_name': channel.get('owner_name', ''),
                    'created_at': channel['created_at'].isoformat() if channel.get('created_at') else None
                }
                if channel.get('profile_image_data'):
                    try:
                        image_bytes = bytes(channel['profile_image_data'])
                        channel_dict['profile_image_base64'] = base64.b64encode(image_bytes).decode('utf-8')
                    except:
                        pass
                channels.append(channel_dict)
        
        return jsonify(channels)
    except Exception as e:
        print(f"Error getting subscriptions: {e}")
        return jsonify([]), 200

# Fix the get_my_channel endpoint to return proper data
@app.route('/api/channel/my', methods=['GET'])
@token_required
def get_my_channel(current_user):
    try:
        channel = mongo.db.channels.find_one({'owner_id': current_user['_id']})
        if not channel:
            return jsonify({'hasChannel': False}), 200
        
        # Get channel posts
        posts = list(mongo.db.posts.find({'channel_id': channel['_id']}).sort('created_at', -1))
        
        channel_dict = {
            '_id': str(channel['_id']),
            'name': channel['name'],
            'description': channel.get('description', ''),
            'owner_id': str(channel['owner_id']),
            'owner_name': channel['owner_name'],
            'subscriber_count': channel.get('subscriber_count', 0),
            'hasChannel': True,
            'posts': []
        }
        
        # Add profile image if exists
        if channel.get('profile_image_data'):
            try:
                image_bytes = bytes(channel['profile_image_data'])
                channel_dict['profile_image_base64'] = base64.b64encode(image_bytes).decode('utf-8')
            except:
                pass
        
        # Add posts
        for post in posts:
            post_dict = {
                '_id': str(post['_id']),
                'title': post.get('title', 'Untitled'),
                'likes': post.get('likes', 0),
                'comments': len(post.get('comments', [])),
                'created_at': post['created_at'].isoformat() if post.get('created_at') else None,
            }
            if post.get('cover_image_data'):
                try:
                    image_bytes = bytes(post['cover_image_data'])
                    post_dict['cover_image_base64'] = base64.b64encode(image_bytes).decode('utf-8')
                except:
                    pass
            channel_dict['posts'].append(post_dict)
        
        return jsonify(channel_dict)
    except Exception as e:
        print(f"Error getting my channel: {e}")
        traceback.print_exc()
        return jsonify({'hasChannel': False}), 200

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        
        user = mongo.db.users.find_one({'email': email})
        if not user or not bcrypt.checkpw(password.encode('utf-8'), user['password']):
            return jsonify({'message': 'Invalid credentials'}), 401
        
        token = jwt.encode({
            'user_id': str(user['_id']),
            'exp': datetime.utcnow() + timedelta(days=7)
        }, app.config['SECRET_KEY'], algorithm='HS256')
        
        # Check if user has a channel
        channel = mongo.db.channels.find_one({'owner_id': user['_id']})
        
        return jsonify({
            'token': token,
            'user': {
                '_id': str(user['_id']),
                'username': user['username'],
                'email': user['email'],
                'points': user.get('points', 0),
                'total_posts': user.get('total_posts', 0),
                'hasChannel': channel is not None,
                'channelId': str(channel['_id']) if channel else None
            }
        })
    except Exception as e:
        print(f"Login error: {e}")
        traceback.print_exc()
        return jsonify({'message': str(e)}), 500

# ==================== CHANNEL ROUTES ====================

@app.route('/api/channel', methods=['POST'])
@token_required
def create_channel(current_user):
    try:
        print("=" * 50)
        print("Creating channel for user:", current_user['username'])
        
        name = request.form.get('name')
        description = request.form.get('description', '')
        profile_image = request.files.get('profile_image') if 'profile_image' in request.files else None
        
        print(f"Name: {name}")
        print(f"Description: {description}")
        print(f"Profile image: {profile_image.filename if profile_image else 'None'}")
        
        if not name:
            return jsonify({'message': 'Channel name is required'}), 400
        
        # Check if user already has a channel
        existing_channel = mongo.db.channels.find_one({'owner_id': current_user['_id']})
        if existing_channel:
            return jsonify({'message': 'Channel already exists'}), 400
        
        profile_image_data = None
        profile_image_filename = None
        
        if profile_image and allowed_file(profile_image.filename):
            profile_image_data = profile_image.read()
            profile_image_filename = secure_filename(profile_image.filename)
            print(f"Profile image size: {len(profile_image_data)} bytes")
        
        channel = {
            'name': name,
            'description': description,
            'profile_image_data': Binary(profile_image_data) if profile_image_data else None,
            'profile_image_filename': profile_image_filename,
            'owner_id': current_user['_id'],
            'owner_name': current_user['username'],
            'subscribers': [],
            'subscriber_count': 0,
            'created_at': datetime.utcnow()
        }
        
        result = mongo.db.channels.insert_one(channel)
        print(f"Channel created with ID: {result.inserted_id}")
        print("=" * 50)
        
        return jsonify({
            'message': 'Channel created',
            'channel_id': str(result.inserted_id)
        })
    except Exception as e:
        print(f"Error creating channel: {e}")
        traceback.print_exc()
        return jsonify({'message': str(e)}), 500
@app.route('/api/channel/<channel_id>', methods=['GET'])
def get_channel(channel_id):
    try:
        channel = mongo.db.channels.find_one({'_id': ObjectId(channel_id)})
        if not channel:
            return jsonify({'message': 'Channel not found'}), 404
        
        # Get channel posts
        posts = list(mongo.db.posts.find({'channel_id': ObjectId(channel_id)}).sort('created_at', -1))
        
        channel_dict = {
            '_id': str(channel['_id']),
            'name': channel['name'],
            'description': channel.get('description', ''),
            'owner_id': str(channel['owner_id']),
            'owner_name': channel['owner_name'],
            'subscriber_count': channel.get('subscriber_count', 0),
            'created_at': channel['created_at'].isoformat() if channel.get('created_at') else None,
            'posts': []
        }
        
        # Add profile image if exists
        if channel.get('profile_image_data'):
            try:
                image_bytes = bytes(channel['profile_image_data'])
                channel_dict['profile_image_base64'] = base64.b64encode(image_bytes).decode('utf-8')
                print(f"Channel logo found for: {channel['name']}")
            except Exception as e:
                print(f"Error converting channel logo: {e}")
                channel_dict['profile_image_base64'] = None
        else:
            print(f"No profile image for channel: {channel['name']}")
            channel_dict['profile_image_base64'] = None
        
        # Add posts
        for post in posts:
            post_dict = {
                '_id': str(post['_id']),
                'title': post.get('title', 'Untitled'),
                'content': post.get('content', ''),
                'likes': post.get('likes', 0),
                'comments': len(post.get('comments', [])),
                'created_at': post['created_at'].isoformat() if post.get('created_at') else None,
            }
            if post.get('cover_image_data'):
                try:
                    image_bytes = bytes(post['cover_image_data'])
                    post_dict['cover_image_base64'] = base64.b64encode(image_bytes).decode('utf-8')
                except:
                    pass
            channel_dict['posts'].append(post_dict)
        
        return jsonify(channel_dict)
    except Exception as e:
        print(f"Error getting channel: {e}")
        traceback.print_exc()
        return jsonify({'message': str(e)}), 500
@app.route('/api/channel/<channel_id>/subscribe', methods=['POST'])
@token_required
def subscribe_channel(current_user, channel_id):
    try:
        # Add subscriber to channel
        mongo.db.channels.update_one(
            {'_id': ObjectId(channel_id)},
            {'$addToSet': {'subscribers': str(current_user['_id'])}, '$inc': {'subscriber_count': 1}}
        )
        # Add channel to user's subscribed list
        mongo.db.users.update_one(
            {'_id': current_user['_id']},
            {'$addToSet': {'subscribed_channels': channel_id}}
        )
        return jsonify({'message': 'Subscribed successfully'})
    except Exception as e:
        print(f"Error subscribing: {e}")
        return jsonify({'message': str(e)}), 500

# ==================== POST ROUTES ====================
@app.route('/api/posts', methods=['GET'])
def get_posts():
    try:
        posts = list(mongo.db.posts.find().sort('created_at', -1).limit(20))
        result = []
        for post in posts:
            # Get channel info
            channel = None
            if post.get('channel_id'):
                channel = mongo.db.channels.find_one({'_id': ObjectId(post['channel_id'])})
            
            post_dict = {
                '_id': str(post['_id']),
                'title': post.get('title', 'Untitled'),
                'category': post.get('category', 'Story'),  # Return category
                'content': post.get('content', ''),
                'channel_id': str(post['channel_id']) if post.get('channel_id') else None,
                'channel_name': channel['name'] if channel else post.get('author_name', 'Anonymous'),
                'author_name': post.get('author_name', 'Anonymous'),
                'likes': post.get('likes', 0),
                'comments': post.get('comments', []),
                'created_at': post['created_at'].isoformat() if post.get('created_at') else None,
            }
            
            # Add channel logo
            if channel and channel.get('profile_image_data'):
                try:
                    image_bytes = bytes(channel['profile_image_data'])
                    post_dict['channel_logo_base64'] = base64.b64encode(image_bytes).decode('utf-8')
                except:
                    post_dict['channel_logo_base64'] = None
            else:
                post_dict['channel_logo_base64'] = None
            
            # Add cover image
            if post.get('cover_image_data'):
                try:
                    image_bytes = bytes(post['cover_image_data'])
                    post_dict['cover_image_base64'] = base64.b64encode(image_bytes).decode('utf-8')
                except:
                    post_dict['cover_image_base64'] = None
            else:
                post_dict['cover_image_base64'] = None
            
            result.append(post_dict)
        return jsonify(result)
    except Exception as e:
        print(f"Error fetching posts: {e}")
        traceback.print_exc()
        return jsonify([]), 200
    
@app.route('/api/posts', methods=['POST'])
@token_required
def create_post(current_user):
    try:
        title = request.form.get('title')
        category = request.form.get('category', 'Story')  # Get category from request
        content = request.form.get('content')
        cover_image = request.files.get('cover_image')
        
        if not title or not content:
            return jsonify({'message': 'Title and content are required'}), 400
        
        # Get user's channel
        channel = mongo.db.channels.find_one({'owner_id': current_user['_id']})
        if not channel:
            return jsonify({'message': 'Please create a channel first'}), 400
        
        cover_image_data = None
        cover_image_filename = None
        
        if cover_image and allowed_file(cover_image.filename):
            cover_image_data = cover_image.read()
            cover_image_filename = secure_filename(cover_image.filename)
        
        post = {
            'title': title,
            'category': category,  # Save category
            'content': content,
            'cover_image_data': Binary(cover_image_data) if cover_image_data else None,
            'cover_image_filename': cover_image_filename,
            'channel_id': channel['_id'],
            'channel_name': channel['name'],
            'author_id': current_user['_id'],
            'author_name': current_user['username'],
            'likes': 0,
            'comments': [],
            'created_at': datetime.utcnow()
        }
        
        result = mongo.db.posts.insert_one(post)
        
        # Update user points and post count
        mongo.db.users.update_one(
            {'_id': current_user['_id']},
            {'$inc': {'points': 200, 'total_posts': 1}}
        )
        
        return jsonify({
            'message': 'Post created',
            'post_id': str(result.inserted_id),
            'points_earned': 200
        })
    except Exception as e:
        print(f"Error creating post: {e}")
        traceback.print_exc()
        return jsonify({'message': str(e)}), 500
@app.route('/api/posts/<post_id>', methods=['GET'])
def get_post(post_id):
    try:
        post = mongo.db.posts.find_one({'_id': ObjectId(post_id)})
        if not post:
            return jsonify({'message': 'Post not found'}), 404
        
        # Get channel info
        channel = mongo.db.channels.find_one({'_id': post['channel_id']}) if post.get('channel_id') else None
        
        post_dict = {
            '_id': str(post['_id']),
            'title': post.get('title', 'Untitled'),
            'content': post.get('content', ''),
            'channel_id': str(post['channel_id']) if post.get('channel_id') else None,
            'channel_name': channel['name'] if channel else None,
            'author_id': str(post.get('author_id', '')),
            'author_name': post.get('author_name', 'Anonymous'),
            'likes': post.get('likes', 0),
            'comments': post.get('comments', []),
            'created_at': post['created_at'].isoformat() if post.get('created_at') else None,
        }
        
        if post.get('cover_image_data'):
            try:
                image_bytes = bytes(post['cover_image_data'])
                post_dict['cover_image_base64'] = base64.b64encode(image_bytes).decode('utf-8')
            except:
                pass
        
        return jsonify(post_dict)
    except Exception as e:
        print(f"Error fetching post: {e}")
        traceback.print_exc()
        return jsonify({'message': str(e)}), 500

@app.route('/api/posts/<post_id>/like', methods=['POST'])
@token_required
def like_post(current_user, post_id):
    try:
        result = mongo.db.posts.update_one(
            {'_id': ObjectId(post_id)},
            {'$inc': {'likes': 1}}
        )
        if result.modified_count == 0:
            return jsonify({'message': 'Post not found'}), 404
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
        result = mongo.db.posts.update_one(
            {'_id': ObjectId(post_id)},
            {'$push': {'comments': comment}}
        )
        return jsonify({'message': 'Comment added'})
    except Exception as e:
        print(f"Error adding comment: {e}")
        return jsonify({'message': str(e)}), 500

# ==================== PROFILE ROUTE ====================

@app.route('/api/profile', methods=['GET'])
@token_required
def get_profile(current_user):
    try:
        user = mongo.db.users.find_one({'_id': current_user['_id']})
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        # Get subscriber count (users who subscribed to user's channel)
        channel = mongo.db.channels.find_one({'owner_id': user['_id']})
        subscriber_count = channel.get('subscriber_count', 0) if channel else 0
        
        return jsonify({
            '_id': str(user['_id']),
            'username': user['username'],
            'email': user['email'],
            'points': user.get('points', 0),
            'total_posts': user.get('total_posts', 0),
            'subscribers': subscriber_count,
            'hasChannel': channel is not None
        })
    except Exception as e:
        print(f"Error fetching profile: {e}")
        traceback.print_exc()
        return jsonify({'message': str(e)}), 500

if __name__ == '__main__':
    
     app.run(debug=False, host='0.0.0.0', port=5001, threaded=True)
