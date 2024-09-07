import yaml
from flask import Flask, request, jsonify, render_template, redirect, url_for
from sqlalchemy import create_engine, Column, Integer, String, Date, text
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import pika
from pika import exceptions
import json
import os

# Wczytanie konfiguracji
script_dir = os.path.dirname(__file__)
with open(script_dir + "/config/config.yaml", "r") as f:
    config = yaml.safe_load(f)
    DATABASE_URL = config["database"]["url"]
    RABBITMQ_HOST = config["rabbitmq"]["host"]
    RABBITMQ_PORT = config["rabbitmq"]["port"]
    RABBITMQ_USER = config["rabbitmq"]["user"]
    RABBITMQ_PASSWORD = config["rabbitmq"]["password"]
    RABBITMQ_VHOST = config["rabbitmq"]["vhost"]
    RABBITMQ_EXCHANGE = config["rabbitmq"]["exchange"]
    PORT = config["service"]["port"]


# Inicjalizacja bazy danych
if not os.path.exists(script_dir + "/data"):
    os.makedirs(script_dir + "/data")
engine = create_engine(
    "sqlite:///" + script_dir + DATABASE_URL, connect_args={"timeout": 10}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Reader(Base):
    __tablename__ = "readers"
    card_number = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    surname = Column(String, index=True, nullable=False)
    date_of_birth = Column(Date, nullable=False)


Base.metadata.create_all(bind=engine)


# Funkcje pomocnicze
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


# Flask API
app = Flask(__name__)


@app.route("/readers", methods=["GET"])
def get_readers():
    db = SessionLocal()
    readers = db.query(Reader).all()
    return (
        jsonify(
            [
                {
                    "numer_karty": reader.card_number,
                    "imie": reader.name,
                    "nazwisko": reader.surname,
                    "data_urodzenia": reader.date_of_birth.strftime("%Y-%m-%d"),
                }
                for reader in readers
            ]
        ),
        200,
    )


@app.route("/", methods=["GET"])
def view_readers():
    db = SessionLocal()
    readers = db.query(Reader)
    print(readers)
    readers = readers.all()
    return render_template("view_readers.html", readers=readers)


@app.route("/add_reader", methods=["GET"])
def view_add_reader_form():
    return render_template("add_reader.html")


@app.route("/add_reader", methods=["POST"])
def add_reader():
    data = request.form
    db = SessionLocal()
    reader = Reader(
        name=data.get("name", "anon"),
        surname=data.get("surname", "anonimowy"),
        date_of_birth=datetime.strptime(
            data.get("date_of_birth", "1000-01-01"), "%Y-%m-%d"
        ).date(),
    )
    db.add(reader)
    db.commit()
    publish_event({"action": "reader_added", "reader_card_number": reader.card_number})
    return redirect(url_for("view_readers"))


@app.route("/delete_reader", methods=["POST"])
def delete_reader():
    card_num = request.form["card_num"]
    db = SessionLocal()
    reader = db.query(Reader).filter(Reader.card_number == card_num).first()
    if reader:
        db.delete(reader)
        db.commit()
        publish_event(
            {"action": "reader_deleted", "reader_card_number": reader.card_number}
        )
        return redirect(url_for("view_readers"))
    else:
        return "Czytelnik nie znaleziony", 404


@app.route("/edit_reader/<int:reader_card_num>", methods=["GET"])
def view_edit_reader_form(reader_card_num):
    db = SessionLocal()
    reader = db.query(Reader).filter(Reader.card_number == reader_card_num).first()
    if reader:
        return render_template("edit_reader.html", reader=reader)
    else:
        return "Czytelnika nie znaleziono", 404


@app.route("/update_reader/<int:reader_card_num>", methods=["POST"])
def update_reader(reader_card_num):
    data = request.form
    db = SessionLocal()
    reader = db.query(Reader).filter(Reader.card_number == reader_card_num).first()
    if reader:
        reader.name = data.get("name", reader.name)
        reader.surname = data.get("surname", reader.surname)
        reader.date_of_birth = datetime.strptime(
            data.get("date_of_birth", reader.date_of_birth), "%Y-%m-%d"
        ).date()
        db.commit()
        publish_event(
            {"action": "reader_updated", "reader_card_number": reader.card_number}
        )
        return redirect(url_for("view_readers"))
    else:
        return "Książka nie znaleziona", 404


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


@app.template_filter("pad")
def pad(value, length):
    return str(value).zfill(length)


if __name__ == "__main__":
    app.run(debug=True, port=PORT)
