from datetime import datetime
from flask_pymongo import PyMongo
import bcrypt
from bson import Binary, ObjectId
import base64

mongo = PyMongo()

class User:
    @staticmethod
    def create_user(username, email, password):
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
        return mongo.db.users.insert_one(user)
    
    @staticmethod
    def find_by_email(email):
        return mongo.db.users.find_one({'email': email})
    
    @staticmethod
    def find_by_id(user_id):
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
        return mongo.db.users.find_one({'_id': user_id})
    
    @staticmethod
    def update_points(user_id, points):
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
        return mongo.db.users.update_one(
            {'_id': user_id},
            {'$inc': {'points': points, 'total_posts': 1}}
        )
    
    @staticmethod
    def subscribe_to_channel(user_id, channel_id):
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
        return mongo.db.users.update_one(
            {'_id': user_id},
            {'$addToSet': {'subscribed_channels': channel_id}}
        )
    
    @staticmethod
    def verify_password(user, password):
        return bcrypt.checkpw(password.encode('utf-8'), user['password'])

class Channel:
    @staticmethod
    def create_channel(name, description, profile_image_data, profile_image_filename, owner_id, owner_name):
        channel = {
            'name': name,
            'description': description,
            'profile_image_data': Binary(profile_image_data) if profile_image_data else None,
            'profile_image_filename': profile_image_filename,
            'owner_id': owner_id,
            'owner_name': owner_name,
            'subscribers': [],
            'subscriber_count': 0,
            'created_at': datetime.utcnow()
        }
        return mongo.db.channels.insert_one(channel)
    
    @staticmethod
    def get_channel_by_id(channel_id):
        if isinstance(channel_id, str):
            channel_id = ObjectId(channel_id)
        channel = mongo.db.channels.find_one({'_id': channel_id})
        if channel:
            channel['_id'] = str(channel['_id'])
            channel['owner_id'] = str(channel['owner_id'])
            if channel.get('profile_image_data'):
                try:
                    image_bytes = bytes(channel['profile_image_data'])
                    channel['profile_image_base64'] = base64.b64encode(image_bytes).decode('utf-8')
                except:
                    channel['profile_image_base64'] = None
            return channel
        return None
    
    @staticmethod
    def get_channel_by_owner(owner_id):
        if isinstance(owner_id, str):
            owner_id = ObjectId(owner_id)
        channel = mongo.db.channels.find_one({'owner_id': owner_id})
        if channel:
            channel['_id'] = str(channel['_id'])
            channel['owner_id'] = str(channel['owner_id'])
            if channel.get('profile_image_data'):
                try:
                    image_bytes = bytes(channel['profile_image_data'])
                    channel['profile_image_base64'] = base64.b64encode(image_bytes).decode('utf-8')
                except:
                    channel['profile_image_base64'] = None
            return channel
        return None
    
    @staticmethod
    def subscribe(channel_id, user_id):
        if isinstance(channel_id, str):
            channel_id = ObjectId(channel_id)
        return mongo.db.channels.update_one(
            {'_id': channel_id},
            {'$addToSet': {'subscribers': user_id}, '$inc': {'subscriber_count': 1}}
        )
    
    @staticmethod
    def unsubscribe(channel_id, user_id):
        if isinstance(channel_id, str):
            channel_id = ObjectId(channel_id)
        return mongo.db.channels.update_one(
            {'_id': channel_id},
            {'$pull': {'subscribers': user_id}, '$inc': {'subscriber_count': -1}}
        )

class Post:
    @staticmethod
    def create_post(title, category, content, cover_image_data, cover_image_filename, channel_id, channel_name, author_id, author_name):
        post = {
            'title': title,
            'category': category,
            'content': content,
            'cover_image_data': Binary(cover_image_data) if cover_image_data else None,
            'cover_image_filename': cover_image_filename,
            'channel_id': channel_id,
            'channel_name': channel_name,
            'author_id': author_id,
            'author_name': author_name,
            'likes': 0,
            'comments': [],
            'created_at': datetime.utcnow()
        }
        return mongo.db.posts.insert_one(post)
    
    @staticmethod
    def get_all_posts(limit=20):
        posts = list(mongo.db.posts.find().sort('created_at', -1).limit(limit))
        result = []
        for post in posts:
            post_dict = {
                '_id': str(post['_id']),
                'title': post.get('title', 'Untitled'),
                'category': post.get('category', 'General'),
                'content': post.get('content', ''),
                'channel_id': str(post.get('channel_id', '')),
                'channel_name': post.get('channel_name', ''),
                'author_id': str(post.get('author_id', '')),
                'author_name': post.get('author_name', 'Anonymous'),
                'likes': post.get('likes', 0),
                'comments': post.get('comments', []),
                'created_at': post['created_at'].isoformat() if post.get('created_at') else datetime.utcnow().isoformat(),
            }
            
            if 'cover_image_data' in post and post['cover_image_data']:
                try:
                    image_bytes = bytes(post['cover_image_data'])
                    post_dict['cover_image_base64'] = base64.b64encode(image_bytes).decode('utf-8')
                except:
                    post_dict['cover_image_base64'] = None
            else:
                post_dict['cover_image_base64'] = None
                
            result.append(post_dict)
        return result
    
    @staticmethod
    def get_posts_by_channel(channel_id):
        if isinstance(channel_id, str):
            channel_id = ObjectId(channel_id)
        posts = list(mongo.db.posts.find({'channel_id': channel_id}).sort('created_at', -1))
        result = []
        for post in posts:
            post_dict = {
                '_id': str(post['_id']),
                'title': post.get('title', 'Untitled'),
                'content': post.get('content', ''),
                'created_at': post['created_at'].isoformat() if post.get('created_at') else datetime.utcnow().isoformat(),
                'likes': post.get('likes', 0),
                'comments': len(post.get('comments', []))
            }
            if 'cover_image_data' in post and post['cover_image_data']:
                try:
                    image_bytes = bytes(post['cover_image_data'])
                    post_dict['cover_image_base64'] = base64.b64encode(image_bytes).decode('utf-8')
                except:
                    post_dict['cover_image_base64'] = None
            result.append(post_dict)
        return result
    
    @staticmethod
    def get_post_by_id(post_id):
        if isinstance(post_id, str):
            post_id = ObjectId(post_id)
        post = mongo.db.posts.find_one({'_id': post_id})
        if post:
            post_dict = {
                '_id': str(post['_id']),
                'title': post.get('title', 'Untitled'),
                'category': post.get('category', 'General'),
                'content': post.get('content', ''),
                'channel_id': str(post.get('channel_id', '')),
                'channel_name': post.get('channel_name', ''),
                'author_id': str(post.get('author_id', '')),
                'author_name': post.get('author_name', 'Anonymous'),
                'likes': post.get('likes', 0),
                'comments': post.get('comments', []),
                'created_at': post['created_at'].isoformat() if post.get('created_at') else datetime.utcnow().isoformat(),
            }
            
            if 'cover_image_data' in post and post['cover_image_data']:
                try:
                    image_bytes = bytes(post['cover_image_data'])
                    post_dict['cover_image_base64'] = base64.b64encode(image_bytes).decode('utf-8')
                except:
                    post_dict['cover_image_base64'] = None
            else:
                post_dict['cover_image_base64'] = None
                
            return post_dict
        return None
    
    @staticmethod
    def add_comment(post_id, comment):
        if isinstance(post_id, str):
            post_id = ObjectId(post_id)
        return mongo.db.posts.update_one(
            {'_id': post_id},
            {'$push': {'comments': comment}}
        )
    
    @staticmethod
    def like_post(post_id):
        if isinstance(post_id, str):
            post_id = ObjectId(post_id)
        return mongo.db.posts.update_one(
            {'_id': post_id},
            {'$inc': {'likes': 1}}
        )
