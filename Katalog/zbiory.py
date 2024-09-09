import yaml
from flask import Flask, request, jsonify, render_template, redirect, url_for
from sqlalchemy import create_engine, Column, Integer, String, Boolean, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import pika
from pika import exceptions
import json
import os
import threading

script_dir = os.path.dirname(__file__)
with open(script_dir + "/config/config.yaml", "r") as f:
    config = yaml.safe_load(f)
    DATABASE_URL = config['database']['url']
    RABBITMQ_HOST = config['rabbitmq']['host']
    RABBITMQ_PORT = config['rabbitmq']['port']
    RABBITMQ_USER = config['rabbitmq']['user']
    RABBITMQ_PASSWORD = config['rabbitmq']['password']
    RABBITMQ_VHOST = config['rabbitmq']['vhost']
    RABBITMQ_EXCHANGE = config['rabbitmq']['exchange']
    PORT = config['service']['port']
    DEBUG = config['service']['debug']

if not os.path.exists('data'):
    os.makedirs('data')
# Inicjalizacja bazy danych
if not os.path.exists(script_dir + "/data"):
    os.makedirs(script_dir + "/data")
engine = create_engine(
    "sqlite:///" + script_dir + DATABASE_URL, connect_args={"timeout": 10}
)
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
    rok = data.get('rok_wydania', None)
    ksiazka = Ksiazka(
        tytul=data['tytul'],
        autor=data.get('autor', None),
        rok_wydania=int(rok) if rok else None,
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
def delete_book():
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
        "id_ksiazki": ksiazka.id,
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


def process_message(ch, method, properties, body):
    event = json.loads(body)
    print(f"Odebrano zdarzenie: {event}")

    # Sprawdzanie, czy zdarzenie to wypożyczenie książki
    db = SessionLocal()

    if event['action'] == 'book_borrowed':
        ksiazka = db.query(Ksiazka).filter(Ksiazka.id == event['book_id']).first()
        if ksiazka:
            if ksiazka.dostepnosc == True:

                publish_event(
                    {"action": "book_borrowed_response", "status": "book_successfully_borrowed", "borrow_id": event['borrow_id'], "book_id": event['book_id']})
            else:
                publish_event(
                    {"action": "book_borrowed_response", "status": "book_borrow_denied", "borrow_id": event['borrow_id'], "book_id": event['book_id']})
        else:
            publish_event(
                {"action": "book_borrowed_response", "status": "book_borrow_denied", "borrow_id": event['borrow_id'],
                 "book_id": event['book_id']})
    elif event['action'] == "book_borrowed_successfully":
        ksiazka = db.query(Ksiazka).filter(Ksiazka.id == event['book_id']).first()
        if ksiazka:
            ksiazka.dostepnosc = False
            db.commit()
            print(f"Książka ID {ksiazka.id} została wypożyczona.")

    elif event['action'] == 'book_returned' or event['action'] == 'borrow_deleted':
        ksiazka = db.query(Ksiazka).filter(Ksiazka.id == event['book_id']).first()
        if ksiazka:
            ksiazka.dostepnosc = True
            db.commit()
            print(f"Książka ID {ksiazka.id} została zwrócona.")
            publish_event(
                {"action": "book_successfully_returned", "borrow_id": event['borrow_id'], "book_id": event['book_id']})
    db.close()


# Funkcja do nasłuchiwania RabbitMQ
def start_rabbitmq_listener():
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    connection = pika.BlockingConnection(pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        virtual_host=RABBITMQ_VHOST,
        credentials=credentials
    ))
    channel = connection.channel()
    channel.exchange_declare(exchange=RABBITMQ_EXCHANGE, exchange_type='fanout')
    result = channel.queue_declare(queue='', exclusive=True)
    queue_name = result.method.queue
    channel.queue_bind(exchange=RABBITMQ_EXCHANGE, queue=queue_name)

    print(' [*] Oczekiwanie na wiadomości. Aby zakończyć naciśnij CTRL+C')

    channel.basic_consume(queue=queue_name, on_message_callback=process_message, auto_ack=True)
    channel.start_consuming()


if __name__ == '__main__':
    # Uruchomienie wątku nasłuchującego RabbitMQ
    listener_thread = threading.Thread(target=start_rabbitmq_listener, daemon=True)
    listener_thread.start()

    # Uruchomienie serwera Flask
    app.run(debug=DEBUG, port=PORT)
