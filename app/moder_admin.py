import hashlib
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from app import db_connector
from bleach import clean
import os
from werkzeug.utils import secure_filename
from mysql.connector.errors import DatabaseError
from auth import can_user

bp = Blueprint('moder_admin', __name__, url_prefix='/moder_admin')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@bp.route('/reviews', methods=['GET', 'POST'])
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
        
        cursor.execute("SELECT reviews.*, books.title AS book_title, users.login AS user_name FROM reviews "
                       "JOIN books ON reviews.book_id = books.id "
                       "JOIN users ON reviews.user_id = users.id "
                       "WHERE reviews.status='На рассмотрении' ORDER BY reviews.date_added DESC")
        reviews = cursor.fetchall()

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
        
        cursor.execute("UPDATE reviews SET status='Одобрено' WHERE id=%s", (review_id,))
        db.commit()

        flash("Рецензия одобрена", category="success")
        
    except DatabaseError as e:
        db.rollback()
        flash(f"Ошибка базы данных: {str(e)}", category="danger")

    finally:
        cursor.close()

    return redirect(url_for('moder_admin.moderate_reviews'))

def reject_review(review_id):
    try:
        db = db_connector.connect()
        cursor = db.cursor()
        
        cursor.execute("UPDATE reviews SET status='Отклонено' WHERE id=%s", (review_id,))
        db.commit()

        flash("Рецензия отклонена", category="success")
        
    except DatabaseError as e:
        db.rollback()
        flash(f"Ошибка базы данных: {str(e)}", category="danger")

    finally:
        cursor.close()

    return redirect(url_for('moder_admin.moderate_reviews'))

@bp.route('/books/<int:book_id>/delete', methods=['POST'])
@can_user('delete')  # Restrict delete access to admin users
def delete_book(book_id):
    db = db_connector.connect()
    cursor = db.cursor()

    try:
        # Delete reviews associated with the book_id
        cursor.execute("DELETE FROM reviews WHERE book_id = %s", (book_id,))
        
        # Delete records from book_genres table that reference the book_id
        cursor.execute("DELETE FROM book_genres WHERE book_id = %s", (book_id,))
        
        # Then delete the book record from books table
        cursor.execute("DELETE FROM books WHERE id = %s", (book_id,))
        
        db.commit()
        flash("Книга и связанные рецензии успешно удалены", 'success')
    
    except DatabaseError as e:
        db.rollback()
        flash(f"Ошибка базы данных: {str(e)}", 'danger')
    
    finally:
        cursor.close()
        db.close()

    return redirect(url_for('index'))

@bp.route('/books/add', methods=['GET', 'POST'])
@can_user('create')
def add_book():
    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        descr = request.form['descr']
        year = request.form['year']
        publisher = request.form['publisher']
        pages = request.form['pages']
        genres = request.form.getlist('genre[]')
        cover_file = request.files['cover']

        if cover_file and allowed_file(cover_file.filename):
            filename = secure_filename(cover_file.filename)
            cover_data = cover_file.read()
            cover_hash = hashlib.md5(cover_data).hexdigest()
            cover_path = os.path.join('static/covers', cover_hash + os.path.splitext(filename)[1])

            db = db_connector.connect()
            cursor = db.cursor()

            try:
                cursor.execute("SELECT id FROM covers WHERE hash = %s", (cover_hash,))
                cover = cursor.fetchone()

                if not cover:
                    cursor.execute("INSERT INTO covers (filename, hash) VALUES (%s, %s)", (filename, cover_hash))
                    db.commit()
                    cover_id = cursor.lastrowid
                else:
                    cover_id = cover['id']

                if not os.path.exists(cover_path):
                    with open(cover_path, 'wb') as f:
                        f.write(cover_data)

                cursor.execute("""
                    INSERT INTO books (title, author, descr, year, publisher, pages, cover_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (title, author, descr, year, publisher, pages, cover_id))
                db.commit()
                book_id = cursor.lastrowid

                for genre_id in genres:
                    cursor.execute("INSERT INTO book_genres (book_id, genre_id) VALUES (%s, %s)", (book_id, genre_id))

                db.commit()
                flash("Книга успешно добавлена", 'success')
                return redirect(url_for('index'))

            except DatabaseError as e:
                db.rollback()
                flash(f"Ошибка базы данных: {str(e)}", 'danger')

            finally:
                cursor.close()
                db.close()
        else:
            flash("Недопустимый формат файла обложки", 'danger')

    db = db_connector.connect()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM genres")
    genres = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('book_add.html', genres=genres)

@bp.route('/books/<int:book_id>/edit', methods=['GET', 'POST'])
@can_user('edit')
def edit_book(book_id):
    db = db_connector.connect()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM books WHERE id = %s", (book_id,))
    book = cursor.fetchone()

    cursor.execute("SELECT id, name FROM genres")
    genres = cursor.fetchall()

    cursor.execute("SELECT genre_id FROM book_genres WHERE book_id = %s", (book_id,))
    selected_genres = [genre['genre_id'] for genre in cursor.fetchall()]

    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        descr = request.form['descr']
        year = request.form['year']
        publisher = request.form['publisher']
        pages = request.form['pages']
        genre = request.form.getlist('genre[]')

        cursor.execute("UPDATE books SET title = %s, author = %s, descr = %s, year = %s, publisher = %s, pages = %s WHERE id = %s",
                       (title, author, descr, year, publisher, pages, book_id))
        db.commit()

        cursor.execute("DELETE FROM book_genres WHERE book_id = %s", (book_id,))

        for genre_id in genre:
            cursor.execute("INSERT INTO book_genres (book_id, genre_id) VALUES (%s, %s)", (book_id, genre_id))

        db.commit()

        flash("Книга успешно обновлена", 'success')
        return redirect(url_for('book_view', book_id=book_id))

    cursor.close()
    db.close()
    return render_template('book_edit.html', book=book, genres=genres, selected_genres=selected_genres)
