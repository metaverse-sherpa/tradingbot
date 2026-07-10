from flask import Blueprint, request, jsonify, g
import time
from database import db_session
import database
from web_api.auth import require_auth

docs_bp = Blueprint('docs_bp', __name__)

def is_user_admin(user):
    if not user: return False
    tg_id = user.get("telegram_chat_id")
    tg_user = None
    if tg_id:
        try:
            tg_user = database.get_user(int(tg_id))
        except:
            pass
    is_super_admin = (tg_id == 1567788633 or user.get("email") == "gilesasp@gmail.com")
    return user.get("is_admin", False) or (tg_user and tg_user.get("is_admin", False)) or is_super_admin

@docs_bp.route('/api/docs', methods=['GET'])
def get_docs():
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT id, title, description, content, url, order_index, created_at FROM Documents ORDER BY order_index ASC, id ASC")
        rows = c.fetchall()
        
    docs = []
    for r in rows:
        docs.append({
            "id": r['id'],
            "title": r['title'],
            "description": r['description'],
            "content": r['content'],
            "url": r['url'],
            "order_index": r['order_index'],
            "created_at": r['created_at']
        })
    return jsonify({"docs": docs}), 200

@docs_bp.route('/api/admin/docs', methods=['POST'])
@require_auth
def create_doc():
    user = getattr(g, 'user', None)
    if not is_user_admin(user):
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.json
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    content = data.get('content', '').strip()
    url = data.get('url', '').strip()
    order_index = int(data.get('order_index', 0))
    
    if not title:
        return jsonify({"error": "Title is required"}), 400
        
    created_at = int(time.time())
    
    with db_session() as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO Documents (title, description, content, url, order_index, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (title, description, content, url, order_index, created_at))
        conn.commit()
        new_id = c.lastrowid
        
    return jsonify({"message": "Document created", "id": new_id}), 201

@docs_bp.route('/api/admin/docs/<int:doc_id>', methods=['PUT'])
@require_auth
def update_doc(doc_id):
    user = getattr(g, 'user', None)
    if not is_user_admin(user):
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.json
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    content = data.get('content', '').strip()
    url = data.get('url', '').strip()
    order_index = int(data.get('order_index', 0))
    
    if not title:
        return jsonify({"error": "Title is required"}), 400
        
    with db_session() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE Documents
            SET title = ?, description = ?, content = ?, url = ?, order_index = ?
            WHERE id = ?
        ''', (title, description, content, url, order_index, doc_id))
        
        if c.rowcount == 0:
            return jsonify({"error": "Document not found"}), 404
            
        conn.commit()
        
    return jsonify({"message": "Document updated"}), 200

@docs_bp.route('/api/admin/docs/<int:doc_id>', methods=['DELETE'])
@require_auth
def delete_doc(doc_id):
    user = getattr(g, 'user', None)
    if not is_user_admin(user):
        return jsonify({"error": "Unauthorized"}), 403
        
    with db_session() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM Documents WHERE id = ?", (doc_id,))
        if c.rowcount == 0:
            return jsonify({"error": "Document not found"}), 404
        conn.commit()
        
    return jsonify({"message": "Document deleted"}), 200
