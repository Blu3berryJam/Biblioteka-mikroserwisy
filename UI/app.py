from datetime import datetime

import requests
from flask import Flask, render_template, jsonify, request, redirect, url_for

app = Flask(__name__)

READER_SERVICE_URL = 'http://localhost:8081'
BOOK_SERVICE_URL = 'http://localhost:8080'
BORROWINGS_SERVICE_URL = 'http://localhost:8082'


def fetch_data_from_service(service_url):
    try:
        response = requests.get(service_url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Błąd podczas pobierania danych z {service_url}: {e}")
        return []


def check_service_health(service_url):
    try:
        response = requests.get(service_url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "ONLINE",
                "database": "online" if data["database"]["status"] == "ok" else "offline",
                "rabbitmq": "online" if data["rabbitmq"]["status"] == "ok" else "offline"
            }
        else:
            return {
                "status": "OFFLINE",
                "database": "offline",
                "rabbitmq": "offline"
            }
    except requests.exceptions.RequestException:
        return {
            "status": "OFFLINE",
            "database": "offline",
            "rabbitmq": "offline"
        }


@app.route('/health')
def health_page():
    services = {
        "Katalog": f"{BOOK_SERVICE_URL}/health",
        "Czytelnicy": f"{READER_SERVICE_URL}/health",
        "Wypożyczenia": f"{BORROWINGS_SERVICE_URL}/health"
    }

    health_status = {
        service_name: check_service_health(service_url)
        for service_name, service_url in services.items()
    }

    return render_template('health.html', health_status=health_status)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/fetch_books')
def fetch_books():
    books_url = f"{BOOK_SERVICE_URL}/books"
    books = fetch_data_from_service(books_url)
    return jsonify(books)


@app.route('/fetch_readers')
def fetch_readers():
    readers_url = f"{READER_SERVICE_URL}/readers"
    readers = fetch_data_from_service(readers_url)
    return jsonify(readers)


@app.route('/fetch_borrowings')
def fetch_borrowings():
    borrowings_url = f"{BORROWINGS_SERVICE_URL}/borrowings"
    borrowings = fetch_data_from_service(borrowings_url)
    return jsonify(borrowings)


# Strona formularza dodawania czytelnika
@app.route('/add_reader_form')
def add_reader_form():
    return render_template('add_reader.html')


@app.route('/add_borrowing_form')
def add_borrowing_form():
    return render_template('add_borrowing.html')


@app.route('/add_book_form')
def add_book_form():
    return render_template('add_book.html')

@app.route('/add_book', methods=['POST'])
def add_book():
    data = {
        'tytul': request.form.get('title'),
        'autor': request.form.get('author', None),
        'rok_wydania': request.form.get('year', None),
        'isbn': request.form.get('isbn'),
        'kategoria': request.form.get('category')
    }
    api_url = f"{BOOK_SERVICE_URL}/add_book"
    try:
        response = requests.post(api_url, data=data, timeout=30)
        print(response.raise_for_status())
    except requests.exceptions.RequestException as e:
        print(f"Błąd podczas dodawania książki: {e}")
    return redirect(url_for('index'))


# Dodawanie czytelnika poprzez API mikroserwisu
@app.route('/add_reader', methods=['POST'])
def add_reader():
    data = {
        'name': request.form.get('name', 'anon'),
        'surname': request.form.get('surname', 'anonimowy'),
        'date_of_birth': request.form.get('date_of_birth', '1000-01-01')
    }
    api_url = f"{READER_SERVICE_URL}/add_reader"
    try:
        response = requests.post(api_url, data=data, timeout=30)
        print(response.raise_for_status())
    except requests.exceptions.RequestException as e:
        print(f"Błąd podczas dodawania czytelnika: {e}")
    return redirect(url_for('index'))


@app.route('/add_borrowing', methods=['POST'])
def add_borrowing():
    data = {
        'ksiazka_id': request.form.get('book_id', None),
        'czytelnik_id': request.form.get('reader_id', None),
        'data_wypozyczenia': request.form.get('borrow_date', '1000-01-01')
    }
    api_url = f"{BORROWINGS_SERVICE_URL}/borrow_book"
    response = requests.post(api_url, data=data, timeout=30)
    print(response.status_code)
    try:
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Błąd podczas wypożyczania: {e}")
    return redirect(url_for('index'))


@app.route('/delete_reader', methods=['POST'])
def delete_reader():
    card_num = request.form.get('card_num')
    api_url = f"{READER_SERVICE_URL}/delete_reader"
    try:
        response = requests.post(api_url, data={'card_num': card_num}, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Błąd podczas usuwania czytelnika: {e}")
    return redirect(url_for('index'))


@app.route('/delete_book', methods=['POST'])
def delete_book():
    book_id = request.form.get('book_id')
    api_url = f"{BOOK_SERVICE_URL}/delete_book"
    try:
        response = requests.post(api_url, data={'book_id': book_id}, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Błąd podczas usuwania książki: {e}")
    return redirect(url_for('index'))


@app.route('/delete_borrowing', methods=['POST'])
def delete_borrowing():
    borrow_id = request.form.get('borrow_id')
    api_url = f"{BORROWINGS_SERVICE_URL}/delete_borrow"
    try:
        response = requests.post(api_url, data={'borrow_id': borrow_id}, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Błąd podczas usuwania wypożyczenia: {e}")
    return redirect(url_for('index'))


@app.route('/return_borrow', methods=['POST'])
def return_borrow():
    borrow_id = request.form.get('borrow_id')
    api_url = f"{BORROWINGS_SERVICE_URL}/return_book"
    try:
        response = requests.post(api_url, data={
            'borrow_id': borrow_id
        }, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Błąd podczas zwracania wypożyczenia: {e}")
    return '', 200


if __name__ == '__main__':
    app.run(debug=True, port=5000)
