from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from app import db_connector  # Импорт вашего db_connector
from mysql.connector.errors import DatabaseError

moder_bp = Blueprint('moder', __name__, url_prefix='/moder')

@moder_bp.route('/reviews', methods=['GET', 'POST'])
def moderate_reviews():
    if not current_user.is_authenticated or not current_user.is_moderator():
        flash("Доступ запрещен", category="warning")
        return redirect(url_for('index'))

    if request.method == 'POST':
        review_id = request.form.get('review_id')
        action = request.form.get('action')

        if action == 'approve':
            approve_review(review_id)
        elif action == 'reject':
            reject_review(review_id)

    try:
        db = db_connector.connect()
        cursor = db.cursor(dictionary=True)
        
        # Получаем список рецензий для модерации
        cursor.execute("SELECT reviews.*, books.title AS book_title, users.login AS user_name FROM reviews "
                       "JOIN books ON reviews.book_id = books.id "
                       "JOIN users ON reviews.user_id = users.id "
                       "WHERE reviews.status='pending' ORDER BY reviews.date_added DESC")
        reviews = cursor.fetchall()

        # Добавим отладочную информацию
        print("Отладочная информация: получено рецензий для модерации -", reviews)

    except DatabaseError as e:
        flash(f"Ошибка базы данных: {str(e)}", category="danger")
        reviews = []

    finally:
        cursor.close()

    return render_template('moderate_reviews.html', reviews=reviews)


def approve_review(review_id):
    try:
        db = db_connector.connect()
        cursor = db.cursor()
        
        # Одобрение рецензии
        cursor.execute("UPDATE reviews SET status='Одобрено' WHERE id=%s", (review_id,))
        db.commit()

        flash("Рецензия одобрена", category="success")
        
    except DatabaseError as e:
        db.rollback()
        flash(f"Ошибка базы данных: {str(e)}", category="danger")

    finally:
        cursor.close()

def reject_review(review_id):
    try:
        db = db_connector.connect()
        cursor = db.cursor()
        
        # Отклонение рецензии
        cursor.execute("UPDATE reviews SET status='Отказано' WHERE id=%s", (review_id,))
        db.commit()

        flash("Рецензия отклонена", category="success")
        
    except DatabaseError as e:
        db.rollback()
        flash(f"Ошибка базы данных: {str(e)}", category="danger")

    finally:
        cursor.close()

    return redirect(url_for('moder.moderate_reviews'))
