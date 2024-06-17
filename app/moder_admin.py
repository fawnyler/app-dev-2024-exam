import hashlib
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from werkzeug.utils import secure_filename
from app import db_connector, app
from auth import can_user
from mysql.connector.errors import DatabaseError
import uuid

bp = Blueprint('moder_admin', __name__, url_prefix='/moder_admin')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def calculate_md5(file_data):
    md5_hash = hashlib.md5()
    md5_hash.update(file_data)
    return md5_hash.hexdigest()

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
        with db_connector.connect() as db:
            cursor = db.cursor(dictionary=True)
            cursor.execute("""
                SELECT reviews.*, books.title AS book_title, users.login AS user_name 
                FROM reviews 
                JOIN books ON reviews.book_id = books.id 
                JOIN users ON reviews.user_id = users.id 
                WHERE reviews.status='На рассмотрении' 
                ORDER BY reviews.date_added DESC
            """)
            reviews = cursor.fetchall()
    except DatabaseError as e:
        flash(f"Ошибка базы данных: {str(e)}", category="danger")
        reviews = []

    return render_template('moderate_reviews.html', reviews=reviews)

def approve_review(review_id):
    try:
        with db_connector.connect() as db:
            cursor = db.cursor()
            cursor.execute("UPDATE reviews SET status='Одобрено' WHERE id=%s", (review_id,))
            db.commit()
            flash("Рецензия одобрена", category="success")
    except DatabaseError as e:
        flash(f"Ошибка базы данных: {str(e)}", category="danger")

    return redirect(url_for('moder_admin.moderate_reviews'))

def reject_review(review_id):
    try:
        with db_connector.connect() as db:
            cursor = db.cursor()
            cursor.execute("UPDATE reviews SET status='Отклонено' WHERE id=%s", (review_id,))
            db.commit()
            flash("Рецензия отклонена", category="success")
    except DatabaseError as e:
        flash(f"Ошибка базы данных: {str(e)}", category="danger")

    return redirect(url_for('moder_admin.moderate_reviews'))

@bp.route('/books/add', methods=['GET', 'POST'])
def add_book():
    title = ''
    author = ''
    descr = ''
    year = ''
    publisher = ''
    pages = ''
    selected_genres = []

    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        descr = request.form['descr']
        year = request.form['year']
        publisher = request.form['publisher']
        pages = request.form['pages']
        genres = request.form.getlist('genre[]')
        cover_file = request.files['cover']

        selected_genres = [int(genre_id) for genre_id in genres]

        if cover_file and allowed_file(cover_file.filename):
            file_extension = os.path.splitext(cover_file.filename)[1].lower() 
            uuid_filename = str(uuid.uuid4()) + file_extension

            cover_data = cover_file.read()
            md5_hash = calculate_md5(cover_data)
            cover_path = os.path.join(app.root_path, 'static/covers', md5_hash + file_extension)

            db = db_connector.connect()
            cursor = db.cursor(dictionary=True)

            try:
                cursor.execute("SELECT id FROM covers WHERE md5_hash = %s", (md5_hash,))
                cover = cursor.fetchone()

                if cover:
                    cover_id = cover['id']
                else:
                    cursor.execute("INSERT INTO covers (filename, md5_hash, mime_type) VALUES (%s, %s, %s)", (uuid_filename, md5_hash, 'image/jpeg'))
                    db.commit()
                    cover_id = cursor.lastrowid

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
        else:
            flash("Недопустимый формат файла обложки", 'danger')

    db = db_connector.connect()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM genres")
    genres = cursor.fetchall()
    cursor.close()

    book = {
        'title': title,
        'author': author,
        'descr': descr,
        'year': year,
        'publisher': publisher,
        'pages': pages
    }

    return render_template('book_add.html', genres=genres, selected_genres=selected_genres, book=book)

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

@bp.route('/books/<int:book_id>/delete', methods=['POST'])
@can_user('delete')
def delete_book(book_id):
    try:
        with db_connector.connect() as db:
            cursor = db.cursor()

            cursor.execute("DELETE FROM reviews WHERE book_id = %s", (book_id,))
            
            cursor.execute("DELETE FROM book_genres WHERE book_id = %s", (book_id,))

            cursor.execute("SELECT cover_id FROM books WHERE id = %s", (book_id,))
            cover_id = cursor.fetchone()

            if cover_id:
                cover_id = cover_id[0]

                cursor.execute("DELETE FROM books WHERE id = %s", (book_id,))

                cursor.execute("SELECT COUNT(*) FROM books WHERE cover_id = %s", (cover_id,))
                book_count = cursor.fetchone()[0]

                if book_count == 0:
                    cursor.execute("DELETE FROM covers WHERE id = %s", (cover_id,))

                db.commit()
                flash("Книга и связанные данные успешно удалены", 'success')
            else:
                flash("Обложка книги не найдена", 'warning')

    except DatabaseError as e:
        flash(f"Ошибка базы данных: {str(e)}", 'danger')

    return redirect(url_for('index'))
