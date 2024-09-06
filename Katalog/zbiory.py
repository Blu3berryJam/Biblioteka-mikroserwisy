from flask import Flask, request, jsonify, render_template, redirect, url_for
from sqlalchemy import create_engine, Column, Integer, String, Boolean, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import pika
from pika import exceptions
import json
import os

if not os.path.exists('data'):
    os.makedirs('data')
DATABASE_URL = "sqlite:///data/katalog.db"
engine = create_engine(DATABASE_URL, connect_args={'timeout': 10})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Ksiazka(Base):
    __tablename__ = "ksiazki"
    id = Column(Integer, primary_key=True, index=True)
    tytul = Column(String, index=True)
    autor = Column(String, index=True)
    rok_wydania = Column(Integer)
    isbn = Column(String)
    kategoria = Column(String)
    dostepnosc = Column(Boolean, default=True)


Base.metadata.create_all(bind=engine)

app = Flask(__name__)

RABBITMQ_HOST = 'cow.rmq2.cloudamqp.com'
RABBITMQ_PORT = 5672
RABBITMQ_USER = 'cablqldr'
RABBITMQ_PASSWORD = '77enssqw-7f3OrFdhyXPqcbINR-tXYfj'
RABBITMQ_VHOST = 'cablqldr'
RABBITMQ_EXCHANGE = 'ksiazki'


def check_rabbitmq_connection():
    try:
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
        connection = pika.BlockingConnection(pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            port=RABBITMQ_PORT,
            virtual_host=RABBITMQ_VHOST,
            credentials=credentials,
            connection_attempts=3,
            retry_delay=5,
            socket_timeout=10
        ))
        connection.close()
        return True, None
    except Exception as e:
        return False, f"{e}"


@app.route('/health', methods=['GET'])
def health_check():
    # Sprawdzanie połączenia z bazą danych
    db_status = "ok"
    db_error = None
    try:
        db = SessionLocal()
        connection = db.connection()
        connection.execute(text("SELECT 1"))
        db.close()
    except Exception as e:
        db_status = "error"
        db_error = str(e)

    # Sprawdzanie połączenia z RabbitMQ
    rabbitmq_status, rabbitmq_error = check_rabbitmq_connection()

    # Zwrócenie wyników w odpowiedzi JSON
    return jsonify({
        "database": {
            "status": db_status,
            "error": db_error
        },
        "rabbitmq": {
            "status": "ok" if rabbitmq_status else "error",
            "error": rabbitmq_error
        }
    }), 200 if db_status == "ok" and rabbitmq_status else 500


def publish_event(event):
    try:
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
        connection = pika.BlockingConnection(pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            port=RABBITMQ_PORT,
            virtual_host=RABBITMQ_VHOST,
            credentials=credentials,
            connection_attempts=3,
            retry_delay=5,
            socket_timeout=10
        ))
        channel = connection.channel()
        channel.exchange_declare(exchange=RABBITMQ_EXCHANGE, exchange_type='fanout')
        channel.basic_publish(exchange=RABBITMQ_EXCHANGE, routing_key='', body=json.dumps(event).encode('utf-8'))
        connection.close()
        print(f"Zdarzenie opublikowane: {event}")
    except exceptions.AMQPConnectionError as e:
        print(f"Błąd połączenia: {e}")
    except exceptions.AMQPChannelError as e:
        print(f"Błąd kanału: {e}")
    except Exception as e:
        print(f"Błąd podczas publikowania zdarzenia do RabbitMQ: {e}")


@app.route('/add_book', methods=['POST'])
def add_book():
    data = request.form
    db = SessionLocal()
    ksiazka = Ksiazka(
        tytul=data['tytul'],
        autor=data['autor'],
        rok_wydania=int(data['rok_wydania']),
        isbn=data['isbn'],
        kategoria=data['kategoria'],
        dostepnosc=True
    )
    db.add(ksiazka)
    db.commit()
    publish_event({"action": "book_added", "book_id": ksiazka.id, "title": ksiazka.tytul})
    return redirect(url_for('view_books'))


@app.route('/update_book/<int:book_id>', methods=['POST'])
def update_book(book_id):
    data = request.form
    db = SessionLocal()
    ksiazka = db.query(Ksiazka).filter(Ksiazka.id == book_id).first()
    if ksiazka:
        ksiazka.tytul = data.get('tytul', ksiazka.tytul)
        ksiazka.autor = data.get('autor', ksiazka.autor)
        ksiazka.rok_wydania = int(data.get('rok_wydania', ksiazka.rok_wydania))
        ksiazka.isbn = data.get('isbn', ksiazka.isbn)
        ksiazka.kategoria = data.get('kategoria', ksiazka.kategoria)
        ksiazka.dostepnosc = data.get('dostepnosc') == 'on'
        db.commit()
        publish_event({"action": "book_updated", "book_id": ksiazka.id, "title": ksiazka.tytul})
        return redirect(url_for('view_books'))
    else:
        return "Książka nie znaleziona", 404


@app.route('/delete_book', methods=['POST'])
def delete_book_form():
    book_id = request.form['book_id']
    db = SessionLocal()
    ksiazka = db.query(Ksiazka).filter(Ksiazka.id == book_id).first()
    if ksiazka:
        db.delete(ksiazka)
        db.commit()
        publish_event({"action": "book_deleted", "book_id": ksiazka.id})
        return redirect(url_for('view_books'))
    else:
        return "Książka nie znaleziona", 404


@app.route('/books', methods=['GET'])
def get_books():
    db = SessionLocal()
    ksiazki = db.query(Ksiazka).all()
    return jsonify([{
        "id": ksiazka.id,
        "tytul": ksiazka.tytul,
        "autor": ksiazka.autor,
        "rok_wydania": ksiazka.rok_wydania,
        "isbn": ksiazka.isbn,
        "kategoria": ksiazka.kategoria,
        "dostepnosc": ksiazka.dostepnosc
    } for ksiazka in ksiazki]), 200


@app.route('/add_books', methods=['GET'])
def index():
    return render_template('add_book.html')


@app.route('/', methods=['GET'])
def view_books():
    db = SessionLocal()
    ksiazki = db.query(Ksiazka).all()
    return render_template('view_books.html', ksiazki=ksiazki)


@app.route('/edit_book/<int:book_id>', methods=['GET'])
def edit_book(book_id):
    db = SessionLocal()
    ksiazka = db.query(Ksiazka).filter(Ksiazka.id == book_id).first()
    if ksiazka:
        return render_template('edit_book.html', ksiazka=ksiazka)
    else:
        return "Książka nie znaleziona", 404


if __name__ == '__main__':
    app.run(debug=True, port=8080)
