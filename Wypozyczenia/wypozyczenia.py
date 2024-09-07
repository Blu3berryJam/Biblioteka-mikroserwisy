from datetime import datetime

import yaml
from flask import Flask, request, jsonify, render_template, redirect, url_for
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Date, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import pika
from pika import exceptions
import json
import os

with open("config/config.yaml", "r") as f:
    config = yaml.safe_load(f)
    DATABASE_URL = config['database']['url']
    RABBITMQ_HOST = config['rabbitmq']['host']
    RABBITMQ_PORT = config['rabbitmq']['port']
    RABBITMQ_USER = config['rabbitmq']['user']
    RABBITMQ_PASSWORD = config['rabbitmq']['password']
    RABBITMQ_VHOST = config['rabbitmq']['vhost']
    RABBITMQ_EXCHANGE = config['rabbitmq']['exchange']
    PORT = config['service']['port']

if not os.path.exists('data'):
    os.makedirs('data')
engine = create_engine(DATABASE_URL, connect_args={'timeout': 10})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Wypozyczenie(Base):
    __tablename__ = "wypozyczenia"
    id = Column(Integer, primary_key=True, index=True)
    ksiazka_id = Column(Integer)
    data_wypozyczenia = Column(Date)
    data_zwrotu = Column(Date)
    czytelnik_id = Column(Integer)


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


@app.route('/add_borrow', methods=['POST'])
def add_borrow():
    data = request.form
    db = SessionLocal()
    wypozyczenie = Wypozyczenie(
        ksiazka_id=int(data['ksiazka_id']),
        data_wypozyczenia=datetime.now().date(),
        data_zwrotu=None,
        czytelnik_id=int(data['czytelnik_id'])
    )
    db.add(wypozyczenie)
    db.commit()
    publish_event({"action": "borrow_added", "borrow_id": wypozyczenie.id, "book_id": wypozyczenie.ksiazka_id})
    return redirect(url_for('view_borrowed_books'))

@app.route('/update_borrow/<int:borrow_id>', methods=['POST'])
def update_borrow(borrow_id):
    data = request.form
    db = SessionLocal()
    wypozyczenie = db.query(Wypozyczenie).filter(Wypozyczenie.id == borrow_id).first()
    if wypozyczenie:
        wypozyczenie.data_wypozyczenia = datetime.strptime(data.get('data_wypozyczenia'), '%Y-%m-%d').date()
        wypozyczenie.data_zwrotu = datetime.strptime(data.get('data_zwrotu'), '%Y-%m-%d').date() if data.get('data_zwrotu') else None
        db.commit()
        publish_event({"action": "borrow_updated", "borrow_id": wypozyczenie.id, "book_id": wypozyczenie.ksiazka_id})
        return redirect(url_for('view_borrowed_books'))
    else:
        return "Wypożyczenie nie znalezione", 404


@app.route('/delete_borrow', methods=['POST'])
def delete_borrow_form():
    borrow_id = request.form['borrow_id']
    db = SessionLocal()
    wypozyczenie = db.query(Wypozyczenie).filter(Wypozyczenie.id == borrow_id).first()
    if wypozyczenie:
        db.delete(wypozyczenie)
        db.commit()
        publish_event({"action": "borrow_deleted", "borrow_id": wypozyczenie.id})
        return redirect(url_for('view_borrowed_books'))
    else:
        return "Wypożyczenie nie znalezione", 404


@app.route('/borrowings', methods=['GET'])
def get_borrowings():
    db = SessionLocal()
    wypozyczenia = db.query(Wypozyczenie).all()
    return jsonify([{
        "id": wypozyczenie.id,
        "ksiazka_id": wypozyczenie.ksiazka_id,
        "data_wypozyczenia": wypozyczenie.data_wypozyczenia.strftime('%Y-%m-%d') if wypozyczenie.data_wypozyczenia else None,
        "data_zwrotu": wypozyczenie.data_zwrotu.strftime('%Y-%m-%d') if wypozyczenie.data_zwrotu else None,
        "czytelnik_id": wypozyczenie.czytelnik_id
    } for wypozyczenie in wypozyczenia]), 200

@app.route('/', methods=['GET'])
def view_borrowed_books():
    db = SessionLocal()
    wypozyczenia = db.query(Wypozyczenie).all()
    return render_template('view_borrowed_books.html', wypozyczenia=wypozyczenia)


@app.route('/add_borrow', methods=['GET'])
def add_borrow_form():
    return render_template('add_borrow.html')


@app.route('/edit_borrow/<int:borrow_id>', methods=['GET'])
def edit_borrow(borrow_id):
    db = SessionLocal()
    wypozyczenie = db.query(Wypozyczenie).filter(Wypozyczenie.id == borrow_id).first()
    if wypozyczenie:
        return render_template('edit_borrow.html', wypozyczenie=wypozyczenie)
    else:
        return "Wypożyczenie nie znalezione", 404


if __name__ == '__main__':
    app.run(debug=True, port=PORT)
