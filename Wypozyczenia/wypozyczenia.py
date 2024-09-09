import json
import os
import threading
import time
from datetime import datetime

import pika
import yaml
from flask import Flask, jsonify, redirect, render_template, request, url_for
from pika import exceptions
from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, String, create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

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
engine = create_engine(
    "sqlite:///" + script_dir + DATABASE_URL, connect_args={"timeout": 10}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Wypozyczenie(Base):
    __tablename__ = "wypozyczenia"
    id = Column(Integer, primary_key=True, index=True)
    ksiazka_id = Column(Integer)
    data_wypozyczenia = Column(Date)
    data_zwrotu = Column(Date)
    czytelnik_id = Column(Integer)
    private_id = Column(Integer, unique=True)


class ID(Base):
    __tablename__ = "id"
    id = Column(Integer, primary_key=True, index=True)
    current_id = Column(Integer, unique=True)


class BORROW_APPROVAL:
    def __init__(self):
        self.borrow_id = None
        self.reader = None
        self.book = None


borrow_status = BORROW_APPROVAL()

Base.metadata.create_all(bind=engine)

app = Flask(__name__)


def clear_borrow_status():
    borrow_status.borrow_id = None
    borrow_status.book = None
    borrow_status.reader = None


def get_current_id():
    db = SessionLocal()
    current_id = db.query(ID).first()
    if not current_id:
        current_id = ID(
            current_id=0
        )
        db.add(current_id)
    else:
        current_id.current_id = current_id.current_id + 1
    id_to_return = current_id.current_id
    db.commit()
    db.close()

    return id_to_return


def check_rabbitmq_connection():
    try:
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                port=RABBITMQ_PORT,
                virtual_host=RABBITMQ_VHOST,
                credentials=credentials,
                connection_attempts=3,
                retry_delay=5,
                socket_timeout=10,
            )
        )
        connection.close()
        return True, None
    except Exception as e:
        return False, f"{e}"


@app.route("/health", methods=["GET"])
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
    return jsonify(
        {
            "database": {"status": db_status, "error": db_error},
            "rabbitmq": {
                "status": "ok" if rabbitmq_status else "error",
                "error": rabbitmq_error,
            },
        }
    ), (200 if db_status == "ok" and rabbitmq_status else 500)


def publish_event(event):
    try:
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                port=RABBITMQ_PORT,
                virtual_host=RABBITMQ_VHOST,
                credentials=credentials,
                connection_attempts=3,
                retry_delay=5,
                socket_timeout=10,
            )
        )
        channel = connection.channel()
        channel.exchange_declare(exchange=RABBITMQ_EXCHANGE, exchange_type="fanout")
        channel.basic_publish(
            exchange=RABBITMQ_EXCHANGE,
            routing_key="",
            body=json.dumps(event).encode("utf-8"),
        )
        connection.close()
        print(f"Zdarzenie opublikowane: {event}")
    except exceptions.AMQPConnectionError as e:
        print(f"Błąd połączenia: {e}")
    except exceptions.AMQPChannelError as e:
        print(f"Błąd kanału: {e}")
    except Exception as e:
        print(f"Błąd podczas publikowania zdarzenia do RabbitMQ: {e}")


@app.route('/borrow_book', methods=['POST'])
def add_borrow():
    data = request.form
    db = SessionLocal()
    wypozyczenie = Wypozyczenie(
        ksiazka_id=int(data["ksiazka_id"]),
        data_wypozyczenia=datetime.strptime(
            data.get("data_wypozyczenia", datetime.now()), "%Y-%m-%d").date(),
        data_zwrotu=None,
        czytelnik_id=int(data["czytelnik_id"]),
        private_id=get_current_id()
    )
    borrow_status.borrow_id = wypozyczenie.private_id

    publish_event(
        {
            "action": "book_borrowed",
            "borrow_id": wypozyczenie.private_id,
            "book_id": wypozyczenie.ksiazka_id,
            "reader_id": wypozyczenie.czytelnik_id,
        }
    )
    start_time = time.time()
    status = 200
    while True:
        if borrow_status.book is True and borrow_status.reader is True:
            db.add(wypozyczenie)
            db.commit()
            publish_event(
                {
                    "action": "book_borrowed_successfully",
                    "book_id": wypozyczenie.ksiazka_id,
                }
            )
            clear_borrow_status()
            break
        elif borrow_status.book is False or borrow_status.reader is False:
            print("Nie udało się wypożyczyć!")
            clear_borrow_status()
            status = 400
            break
        elif time.time() - start_time > 10:
            print("Limit czasu osiągnięty!")
            clear_borrow_status()
            status = 408
            break

    return redirect(url_for("view_borrowed_books")), status


@app.route('/return_book', methods=['POST'])
def return_book():
    borrow_id = request.form['borrow_id']
    db = SessionLocal()

    wypozyczenie = db.query(Wypozyczenie).filter_by(id=borrow_id).first()
    if wypozyczenie:
        wypozyczenie.data_zwrotu = datetime.now()
        db.commit()

        # Wysyłamy zdarzenie do RabbitMQ
        publish_event(
            {
                "action": "book_returned",
                "borrow_id": wypozyczenie.private_id,
                "book_id": wypozyczenie.ksiazka_id,
            }
        )

    return redirect(url_for("view_borrowed_books"))


@app.route("/update_borrow/<int:borrow_id>", methods=["POST"])
def update_borrow(borrow_id):
    data = request.form
    db = SessionLocal()
    wypozyczenie = db.query(Wypozyczenie).filter(Wypozyczenie.id == borrow_id).first()
    if wypozyczenie:
        if data.get("data_wypozyczenia"):
            wypozyczenie.data_wypozyczenia = datetime.strptime(
                data.get("data_wypozyczenia"), "%Y-%m-%d"
            ).date()
        wypozyczenie.data_zwrotu = (
            datetime.strptime(data.get("data_zwrotu"), "%Y-%m-%d").date()
            if data.get("data_zwrotu")
            else None
        )
        db.commit()
        publish_event(
            {
                "action": "borrow_updated",
                "borrow_id": wypozyczenie.id,
                "book_id": wypozyczenie.ksiazka_id,
            }
        )
        return redirect(url_for("view_borrowed_books"))
    else:
        return "Wypożyczenie nie znalezione", 404


@app.route("/delete_borrow", methods=["POST"])
def delete_borrow():
    borrow_id = request.form["borrow_id"]
    db = SessionLocal()
    wypozyczenie = db.query(Wypozyczenie).filter(Wypozyczenie.id == borrow_id).first()
    if wypozyczenie:
        db.delete(wypozyczenie)
        db.commit()
        if wypozyczenie.data_zwrotu is None:
            publish_event(
                {
                    "action": "borrow_deleted",
                    "borrow_id": wypozyczenie.id,
                    "book_id": wypozyczenie.ksiazka_id,
                }
            )
        return redirect(url_for("view_borrowed_books")), 202
    else:
        return "Wypożyczenie nie znalezione", 404


@app.route("/borrowings", methods=["GET"])
def get_borrowings():
    db = SessionLocal()
    wypozyczenia = db.query(Wypozyczenie).all()
    return (
        jsonify(
            [
                {
                    "id_wypozyczenia": wypozyczenie.id,
                    "ksiazka_id": wypozyczenie.ksiazka_id,
                    "data_wypozyczenia": (
                        wypozyczenie.data_wypozyczenia.strftime("%Y-%m-%d")
                        if wypozyczenie.data_wypozyczenia
                        else None
                    ),
                    "data_zwrotu": (
                        wypozyczenie.data_zwrotu.strftime("%Y-%m-%d")
                        if wypozyczenie.data_zwrotu
                        else None
                    ),
                    "czytelnik_id": wypozyczenie.czytelnik_id,
                }
                for wypozyczenie in wypozyczenia
            ]
        ),
        200,
    )


@app.route("/", methods=["GET"])
def view_borrowed_books():
    db = SessionLocal()
    wypozyczenia = db.query(Wypozyczenie).all()
    return render_template("view_borrowed_books.html", wypozyczenia=wypozyczenia)


@app.route('/borrow_book', methods=['GET'])
def add_borrow_form():
    return render_template("add_borrow.html")


@app.route("/edit_borrow/<int:borrow_id>", methods=["GET"])
def edit_borrow(borrow_id):
    db = SessionLocal()
    wypozyczenie = db.query(Wypozyczenie).filter(Wypozyczenie.id == borrow_id).first()
    if wypozyczenie:
        return render_template("edit_borrow.html", wypozyczenie=wypozyczenie)
    else:
        return "Wypożyczenie nie znalezione", 404


# Funkcja do przetwarzania wiadomości z RabbitMQ
def process_message(ch, method, properties, body):
    event = json.loads(body)
    print(f"Odebrano zdarzenie: {event}")

    if event["action"] == "book_borrowed_response":
        if event["status"] == "book_successfully_borrowed":
            if borrow_status.borrow_id == event["borrow_id"]:
                borrow_status.book = True
        elif event["status"] == "reader_exist":
            if borrow_status.borrow_id == event["borrow_id"]:
                borrow_status.reader = True
        elif event["status"] == "book_borrow_denied" or event["status"] == "reader_not_exist":
            if borrow_status.borrow_id == event["borrow_id"]:
                borrow_status.book = False
                borrow_status.reader = False
            print(
                f"Próba wypożyczenia książki ID {event['book_id']} została odrzucona."
            )


# Funkcja do nasłuchiwania RabbitMQ
def start_rabbitmq_listener():
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            port=RABBITMQ_PORT,
            virtual_host=RABBITMQ_VHOST,
            credentials=credentials,
        )
    )
    channel = connection.channel()
    channel.exchange_declare(exchange=RABBITMQ_EXCHANGE, exchange_type="fanout")
    result = channel.queue_declare(queue="", exclusive=True)
    queue_name = result.method.queue
    channel.queue_bind(exchange=RABBITMQ_EXCHANGE, queue=queue_name)

    print(" [*] Oczekiwanie na wiadomości. Aby zakończyć naciśnij CTRL+C")

    channel.basic_consume(
        queue=queue_name, on_message_callback=process_message, auto_ack=True
    )
    channel.start_consuming()


if __name__ == "__main__":
    listener_thread = threading.Thread(target=start_rabbitmq_listener, daemon=True)
    listener_thread.start()
    app.run(debug=DEBUG, port=PORT)
