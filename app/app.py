from flask import Flask, jsonify, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from mysqldb import DBConnector
from mysql.connector.errors import DatabaseError
import markdown
import bleach

app = Flask(__name__)
application = app
app.config.from_pyfile('config.py')

db_connector = DBConnector(app)
app.config['DB_CONNECTOR'] = db_connector

from auth import bp as auth_bp, init_login_manager
app.register_blueprint(auth_bp)
init_login_manager(app)

from moder_admin import bp as moder_admin_bp
app.register_blueprint(moder_admin_bp)

def search_by_title(title):
    try:
        db = db_connector.connect()
        cursor = db.cursor(dictionary=True)
        cursor.execute("""
            SELECT 
                books.id,
                books.title,
                books.author,
                books.year,
                GROUP_CONCAT(DISTINCT genres.name ORDER BY genres.name SEPARATOR ', ') AS genre
            FROM 
                books
            LEFT JOIN 
                book_genres ON books.id = book_genres.book_id
            LEFT JOIN 
                genres ON book_genres.genre_id = genres.id
            WHERE 
                books.title LIKE %s
            GROUP BY 
                books.id
        """, ('%' + title + '%',))
        results = cursor.fetchall()
        cursor.close()
        print(f"Search by title '{title}': {results}")
        return results
    except DatabaseError as e:
        flash(f"Ошибка при поиске по названию: {str(e)}", category="danger")
        db_connector.connect().rollback()
        return []

def search_by_genre(genre):
    try:
        db = db_connector.connect()
        cursor = db.cursor(dictionary=True)
        cursor.execute("""
            SELECT 
                books.id, 
                books.title, 
                books.author, 
                books.year,
                GROUP_CONCAT(DISTINCT genres.name ORDER BY genres.name SEPARATOR ', ') AS genre
            FROM 
                books
            JOIN 
                book_genres ON books.id = book_genres.book_id 
            JOIN 
                genres ON book_genres.genre_id = genres.id 
            WHERE 
                genres.name LIKE %s
            GROUP BY 
                books.id
        """, ('%' + genre + '%',))
        results = cursor.fetchall()
        cursor.close()
        print(f"Search by genre '{genre}': {results}")
        return results
    except DatabaseError as e:
        flash(f"Ошибка при поиске по жанру: {str(e)}", category="danger")
        db_connector.connect().rollback()
        return []

def search_by_author(author):
    try:
        db = db_connector.connect()
        cursor = db.cursor(dictionary=True)
        cursor.execute("""
            SELECT 
                books.id,
                books.title,
                books.author,
                books.year,
                GROUP_CONCAT(DISTINCT genres.name ORDER BY genres.name SEPARATOR ', ') AS genre
            FROM 
                books
            LEFT JOIN 
                book_genres ON books.id = book_genres.book_id
            LEFT JOIN 
                genres ON book_genres.genre_id = genres.id
            WHERE 
                books.author LIKE %s
            GROUP BY 
                books.id
        """, ('%' + author + '%',))
        results = cursor.fetchall()
        cursor.close()
        print(f"Search by author '{author}': {results}")
        return results
    except DatabaseError as e:
        flash(f"Ошибка при поиске по автору: {str(e)}", category="danger")
        db_connector.connect().rollback()
        return []

@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query', '')
    
    if query:
        title_results = search_by_title(query)
        genre_results = search_by_genre(query)
        author_results = search_by_author(query)
        
        results = title_results + genre_results + author_results
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(results=results)
        else:
            if results:
                return render_template('search_results.html', books=results, search_query=query)
            else:
                flash('Книги по вашему запросу не найдены.', category='warning')
                return render_template('search_results.html', books=[], search_query=query)
    
    return render_template('search_results.html', books=[], search_query=query)

def get_books(page, per_page):
    try:
        offset = (page - 1) * per_page
        db = db_connector.connect()
        cursor = db.cursor(dictionary=True)
        query = """
            SELECT 
                books.id,
                books.title,  
                books.author,
                books.year,
                GROUP_CONCAT(DISTINCT genres.name ORDER BY genres.name SEPARATOR ', ') AS genre,
                ROUND(AVG(reviews.rating), 2) AS rating,
                COUNT(reviews.id) AS rate_amount
            FROM 
                books
            LEFT JOIN 
                book_genres ON books.id = book_genres.book_id
            LEFT JOIN 
                genres ON book_genres.genre_id = genres.id
            LEFT JOIN 
                reviews ON books.id = reviews.book_id AND reviews.status = 'Одобрено'
            GROUP BY 
                books.id
            ORDER BY 
                books.year DESC 
            LIMIT %s OFFSET %s
        """

        cursor.execute(query, (per_page, offset))
        books = cursor.fetchall()
        cursor.close()

        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) AS total FROM books")
        total_books = cursor.fetchone()['total']
        cursor.close()
        
        return books, total_books
    except DatabaseError as e:
        flash(f"Ошибка получения новых книг: {str(e)}", category="danger")
        db_connector.connect().rollback()
        return [], 0
  
@app.route('/book/<int:book_id>')
def book_view(book_id):
    try:
        db = db_connector.connect()
        cursor = db.cursor(dictionary=True)

        query_book = """
            SELECT 
                books.id,
                books.title,  
                books.author,
                books.publisher,
                books.pages,
                covers.filename AS photo_url,
                books.year,
                GROUP_CONCAT(DISTINCT genres.name ORDER BY genres.name SEPARATOR ', ') AS genre,
                books.descr,
                ROUND(AVG(reviews.rating), 2) AS rating,
                COUNT(reviews.id) AS rate_amount
            FROM 
                books
            LEFT JOIN 
                covers ON books.cover_id = covers.id
            LEFT JOIN 
                book_genres ON books.id = book_genres.book_id
            LEFT JOIN 
                genres ON book_genres.genre_id = genres.id
            LEFT JOIN 
                reviews ON books.id = reviews.book_id AND reviews.status = 'Одобрено'
            WHERE books.id = %s
            GROUP BY books.id
        """
        cursor.execute(query_book, (book_id,))
        book = cursor.fetchone()
        cursor.close()

        if book:
            if book['genre']:
                book['genres_list'] = book['genre'].split(', ')
            else:
                book['genres_list'] = []

            cursor = db.cursor()
            query_review_count = """
                SELECT 
                    COUNT(*) AS visible_review_count
                FROM 
                    reviews
                WHERE 
                    book_id = %s AND status = 'Одобрено'
            """
            cursor.execute(query_review_count, (book_id,))
            review_count = cursor.fetchone()[0]
            cursor.close()

            cursor = db.cursor(dictionary=True)
            query_reviews = """
                SELECT 
                    reviews.id,
                    reviews.rating,
                    reviews.text,
                    reviews.date_added,
                    users.login AS username,
                    reviews.user_id
                FROM 
                    reviews
                JOIN 
                    users ON reviews.user_id = users.id
                WHERE 
                    reviews.book_id = %s AND reviews.status = 'Одобрено'
                ORDER BY 
                    reviews.date_added DESC
            """
            cursor.execute(query_reviews, (book_id,))
            reviews_data = cursor.fetchall()
            cursor.close()

            user_review = None
            if current_user.is_authenticated:
                user_id = current_user.id
                for review in reviews_data:
                    if review['user_id'] == user_id:
                        user_review = review
                        break

            book['descr_html'] = markdown.markdown(book['descr']) if book['descr'] else ""

            for review in reviews_data:
                review['text_html'] = markdown.markdown(review['text'])

            return render_template('book_view.html', book=book, reviews=reviews_data, user_review=user_review, visible_review_count=review_count)
        else:
            flash("Книга не найдена", category="danger")
            return redirect(url_for('index'))
    except DatabaseError as e:
        flash(f"Ошибка получения данных о книге: {str(e)}", category="danger")
        db_connector.connect().rollback()
        return redirect(url_for('index'))


@app.route('/book/<int:book_id>/review', methods=['GET', 'POST'])
@login_required
def add_review(book_id):
    if request.method == 'POST':
        rating = request.form['rating']
        text = request.form['text']
        sanitized_text = bleach.clean(text)

        try:
            db = db_connector.connect()
            cursor = db.cursor(dictionary=True)

            query_check = """
                SELECT id, status FROM reviews WHERE book_id = %s AND user_id = %s
                ORDER BY date_added DESC LIMIT 1
            """
            cursor.execute(query_check, (book_id, current_user.id))
            existing_review = cursor.fetchone()

            if existing_review:
                if existing_review['status'] in ['На рассмотрении', 'Одобрено']:
                    flash('Вы уже оставляли рецензию на эту книгу.', category='danger')
                    return redirect(url_for('book_view', book_id=book_id))

            query = """
                INSERT INTO reviews (book_id, user_id, rating, text, date_added, status)
                VALUES (%s, %s, %s, %s, NOW(), 'На рассмотрении')
            """
            cursor.execute(query, (book_id, current_user.id, rating, sanitized_text))
            db.commit()
            cursor.close()
            flash('Рецензия успешно добавлена и ожидает модерации!', category='success')
            return redirect(url_for('book_view', book_id=book_id))

        except DatabaseError as e:
            flash(f"Ошибка добавления рецензии: {str(e)}", category="danger")
            db_connector.connect().rollback()
            print(f"DatabaseError: {str(e)}")
            return redirect(url_for('book_view', book_id=book_id))

        except Exception as e:
            flash(f"Произошла неожиданная ошибка: {str(e)}", category="danger")
            print(f"Unexpected error: {str(e)}")
            return redirect(url_for('book_view', book_id=book_id))

    return render_template('add_review.html', book_id=book_id)

@app.route('/')
def index():
    search_query = request.args.get('query', '')
    
    if search_query:
        # Если есть поисковый запрос, ищем книгу по названию, жанру и автору
        title_results = search_by_title(search_query)
        genre_results = search_by_genre(search_query)
        author_results = search_by_author(search_query)

        results = title_results + genre_results + author_results
        
        # Убираем дублирующиеся книги из результатов
        seen = set()
        unique_results = []
        for book in results:
            if book['id'] not in seen:
                unique_results.append(book)
                seen.add(book['id'])

        if unique_results:
            return render_template('search_results.html', books=unique_results, search_query=search_query)
        else:
            flash('Книга не найдена', category='warning')
            return redirect(url_for('index'))
    
    # Ваш текущий код для отображения всех книг на главной странице
    per_page = 5
    page = request.args.get('page', 1, type=int)
    books, total_books = get_books(page, per_page)
    total_pages = (total_books + per_page - 1) // per_page
    return render_template('index.html', books=books, page=page, total_pages=total_pages)

if __name__ == '__main__':
    app.run(debug=True)
