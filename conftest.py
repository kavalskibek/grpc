import grpc
import pytest
import psycopg2
import pika
import json
import os
from faker import Faker
from dotenv import load_dotenv

# Generated from proto — run generate_proto.sh first
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "generated"))
import booking_pb2
import booking_pb2_grpc

load_dotenv()

fake = Faker()

GRPC_HOST = os.getenv("GRPC_HOST", "localhost")
GRPC_PORT = os.getenv("GRPC_PORT", "50051")

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "database": os.getenv("POSTGRES_DB", "bookings"),
    "user": os.getenv("POSTGRES_USER", "qa"),
    "password": os.getenv("POSTGRES_PASSWORD", "qa123"),
}

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")


# ── gRPC channel ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def grpc_channel():
    channel = grpc.insecure_channel(f"{GRPC_HOST}:{GRPC_PORT}")
    yield channel
    channel.close()


@pytest.fixture(scope="session")
def booking_stub(grpc_channel):
    return booking_pb2_grpc.BookingServiceStub(grpc_channel)


# ── Database ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def db():
    conn = psycopg2.connect(**DB_CONFIG)
    yield conn
    conn.close()


@pytest.fixture
def db_cursor(db):
    cur = db.cursor()
    yield cur
    db.rollback()
    cur.close()


# ── RabbitMQ ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def rabbitmq_channel():
    params = pika.URLParameters(RABBITMQ_URL)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    channel.exchange_declare(exchange="booking_events", exchange_type="topic", durable=True)
    yield channel
    connection.close()


@pytest.fixture
def consume_event(rabbitmq_channel):
    """Helper to consume one event from RabbitMQ and return parsed payload."""
    def _consume(routing_key: str, timeout: int = 5):
        result = rabbitmq_channel.queue_declare(queue="", exclusive=True)
        queue_name = result.method.queue
        rabbitmq_channel.queue_bind(
            exchange="booking_events",
            queue=queue_name,
            routing_key=routing_key,
        )
        messages = []

        def callback(ch, method, properties, body):
            messages.append(json.loads(body))
            ch.basic_ack(delivery_tag=method.delivery_tag)

        rabbitmq_channel.basic_consume(queue=queue_name, on_message_callback=callback)
        rabbitmq_channel.connection.process_data_events(time_limit=timeout)
        rabbitmq_channel.queue_delete(queue=queue_name)
        return messages[0] if messages else None

    return _consume


# ── Factories ─────────────────────────────────────────────────────────────────

@pytest.fixture
def booking_payload():
    """Valid booking payload factory."""
    def _factory(**overrides):
        payload = {
            "user_id": str(fake.uuid4()),
            "hotel_id": str(fake.uuid4()),
            "room_type": fake.random_element(["STANDARD", "DELUXE", "SUITE"]),
            "check_in": "2026-07-01",
            "check_out": "2026-07-05",
            "price": float(fake.random_int(min=100, max=1000)),
        }
        payload.update(overrides)
        return payload
    return _factory


@pytest.fixture
def created_booking(booking_stub, booking_payload):
    """Creates a booking and cleans up after test."""
    payload = booking_payload()
    request = booking_pb2.CreateBookingRequest(**payload)
    response = booking_stub.CreateBooking(request)
    yield response
    # Cleanup — cancel booking after test
    try:
        booking_stub.CancelBooking(
            booking_pb2.CancelBookingRequest(
                booking_id=response.booking_id,
                reason="test cleanup"
            )
        )
    except grpc.RpcError:
        pass
