from flask import Blueprint, request, jsonify, g
import time
from database import db_session
import database
from web_api.auth import require_auth

faq_bp = Blueprint('faq_bp', __name__)

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

@faq_bp.route('/api/faq', methods=['GET'])
def get_faqs():
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT id, question, answer, order_index, created_at FROM FAQs ORDER BY order_index ASC, id ASC")
        rows = c.fetchall()
        
    faqs = []
    for r in rows:
        faqs.append({
            "id": r['id'],
            "question": r['question'],
            "answer": r['answer'],
            "order_index": r['order_index'],
            "created_at": r['created_at']
        })
    return jsonify({"faqs": faqs}), 200

@faq_bp.route('/api/admin/faq', methods=['POST'])
@require_auth
def create_faq():
    user = getattr(g, 'user', None)
    if not is_user_admin(user):
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.json
    question = data.get('question', '').strip()
    answer = data.get('answer', '').strip()
    order_index = int(data.get('order_index', 0))
    
    if not question or not answer:
        return jsonify({"error": "Question and answer are required"}), 400
        
    created_at = int(time.time())
    
    with db_session() as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO FAQs (question, answer, order_index, created_at)
            VALUES (?, ?, ?, ?)
        ''', (question, answer, order_index, created_at))
        conn.commit()
        new_id = c.lastrowid
        
    return jsonify({"message": "FAQ created", "id": new_id}), 201

@faq_bp.route('/api/admin/faq/<int:faq_id>', methods=['PUT'])
@require_auth
def update_faq(faq_id):
    user = getattr(g, 'user', None)
    if not is_user_admin(user):
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.json
    question = data.get('question', '').strip()
    answer = data.get('answer', '').strip()
    order_index = int(data.get('order_index', 0))
    
    if not question or not answer:
        return jsonify({"error": "Question and answer are required"}), 400
        
    with db_session() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE FAQs
            SET question = ?, answer = ?, order_index = ?
            WHERE id = ?
        ''', (question, answer, order_index, faq_id))
        
        if conn.changes() == 0:
            return jsonify({"error": "FAQ not found"}), 404
            
        conn.commit()
        
    return jsonify({"message": "FAQ updated"}), 200

@faq_bp.route('/api/admin/faq/<int:faq_id>', methods=['DELETE'])
@require_auth
def delete_faq(faq_id):
    user = getattr(g, 'user', None)
    if not is_user_admin(user):
        return jsonify({"error": "Unauthorized"}), 403
        
    with db_session() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM FAQs WHERE id = ?", (faq_id,))
        if conn.changes() == 0:
            return jsonify({"error": "FAQ not found"}), 404
        conn.commit()
        
    return jsonify({"message": "FAQ deleted"}), 200
