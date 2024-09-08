import requests
from flask import Flask, render_template, jsonify, request, redirect, url_for

app = Flask(__name__)

# Funkcja do pobierania danych z API mikroserwisu
def fetch_data_from_service(service_url):
    try:
        response = requests.get(service_url)
        response.raise_for_status()  # Sprawdzamy, czy nie ma błędu HTTP
        return response.json()  # Zwracamy dane w formacie JSON
    except requests.exceptions.RequestException as e:
        print(f"Błąd podczas pobierania danych z {service_url}: {e}")
        return []  # Zwracamy pustą listę w przypadku błędu

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/fetch_books')
def fetch_books():
    books_url = 'http://localhost:8080/books'
    books = fetch_data_from_service(books_url)
    return jsonify(books)

@app.route('/fetch_readers')
def fetch_readers():
    readers_url = 'http://localhost:8081/readers'
    readers = fetch_data_from_service(readers_url)
    return jsonify(readers)

@app.route('/fetch_borrowings')
def fetch_borrowings():
    borrowings_url = 'http://localhost:8082/borrowings'
    borrowings = fetch_data_from_service(borrowings_url)
    return jsonify(borrowings)

# Strona formularza dodawania czytelnika
@app.route('/add_reader_form')
def add_reader_form():
    return render_template('add_reader.html')

# Dodawanie czytelnika poprzez API mikroserwisu
@app.route('/add_reader', methods=['POST'])
def add_reader():
    data = {
        'name': request.form.get('name', 'anon'),
        'surname': request.form.get('surname', 'anonimowy'),
        'date_of_birth': request.form.get('date_of_birth', '1000-01-01')
    }
    # Adres URL API mikroserwisu do dodawania czytelników
    api_url = 'http://localhost:8081/add_reader'
    try:
        response = requests.post(api_url, data=data)
        response.raise_for_status()  # Sprawdzamy, czy nie ma błędu HTTP
    except requests.exceptions.RequestException as e:
        print(f"Błąd podczas dodawania czytelnika: {e}")
    return redirect(url_for('index'))  # Powrót do strony głównej

if __name__ == '__main__':
    app.run(debug=True, port=5000)
