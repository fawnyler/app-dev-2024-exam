from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from app import db_connector  # Import your db_connector as needed
from bleach import clean
import hashlib
import os
from werkzeug.utils import secure_filename
from mysql.connector.errors import DatabaseError

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@admin_bp.route('/book/edit/<int:book_id>', methods=['GET', 'POST'])
def book_edit(book_id):
    if not current_user.is_admin():
        flash("У вас недостаточно прав для выполнения этого действия", category="warning")
        return redirect(url_for('index'))

    try:
        db = db_connector.connect()
        cursor = db.cursor(dictionary=True)
        
        # Fetch book information
        cursor.execute("SELECT * FROM books WHERE id=%s", (book_id,))
        book = cursor.fetchone()

        if not book:
            flash("Книга не найдена", category="danger")
            return redirect(url_for('index'))

        # Fetch genres list
        cursor.execute("SELECT id, name FROM genres ORDER BY name")
        genres = cursor.fetchall()

        if request.method == 'POST':
            title = request.form['title']
            author = request.form['author']
            year = request.form['year']
            descr = request.form['descr']
            genre = request.form.getlist('genre')

            sanitized_descr = clean(descr, tags=['p', 'br', 'em', 'strong', 'ul', 'ol', 'li'])

            try:
                # Update book information
                cursor.execute("UPDATE books SET title=%s, author=%s, year=%s, descr=%s WHERE id=%s",
                               (title, author, year, sanitized_descr, book_id))
                db.commit()

                # Delete old book-genre associations
                cursor.execute("DELETE FROM book_genres WHERE book_id=%s", (book_id,))
                db.commit()

                # Insert new book-genre associations
                for genre_id in genre:
                    cursor.execute("INSERT INTO book_genres (book_id, genre_id) VALUES (%s, %s)", (book_id, genre_id))
                db.commit()

                flash("Книга успешно отредактирована", category="success")
                return redirect(url_for('book_view', book_id=book_id))

            except DatabaseError as e:
                db.rollback()
                flash(f"Ошибка при редактировании книги: {str(e)}", category="danger")

            finally:
                cursor.close()

    except DatabaseError as e:
        flash(f"Ошибка при загрузке данных о книге: {str(e)}", category="danger")

    return render_template('book_edit.html', book=book, genres=genres)
