import grpc
import uuid
import json
import psycopg2
import pika
from concurrent import futures
from datetime import datetime
import booking_pb2
import booking_pb2_grpc
import os

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "postgres"),
    "port": os.getenv("POSTGRES_PORT", 5432),
    "database": os.getenv("POSTGRES_DB", "bookings"),
    "user": os.getenv("POSTGRES_USER", "qa"),
    "password": os.getenv("POSTGRES_PASSWORD", "qa123"),
}

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")


def get_db():
    return psycopg2.connect(**DB_CONFIG)


def publish_event(event_type: str, payload: dict):
    try:
        params = pika.URLParameters(RABBITMQ_URL)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.exchange_declare(exchange="booking_events", exchange_type="topic", durable=True)
        channel.basic_publish(
            exchange="booking_events",
            routing_key=event_type,
            body=json.dumps(payload),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,
            ),
        )
        connection.close()
    except Exception as e:
        print(f"RabbitMQ publish error: {e}")


class BookingServicer(booking_pb2_grpc.BookingServiceServicer):

    def CreateBooking(self, request, context):
        # Validate required fields
        if not request.user_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "user_id is required")
        if not request.hotel_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "hotel_id is required")
        if not request.check_in or not request.check_out:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "check_in and check_out are required")
        if request.price <= 0:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "price must be greater than 0")

        booking_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()

        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO bookings (id, user_id, hotel_id, room_type, check_in, check_out, price, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    booking_id,
                    request.user_id,
                    request.hotel_id,
                    request.room_type,
                    request.check_in,
                    request.check_out,
                    request.price,
                    "CONFIRMED",
                    created_at,
                ),
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            context.abort(grpc.StatusCode.INTERNAL, f"Database error: {e}")

        # Publish event to RabbitMQ
        publish_event("booking.created", {
            "booking_id": booking_id,
            "user_id": request.user_id,
            "hotel_id": request.hotel_id,
            "price": request.price,
            "status": "CONFIRMED",
        })

        return booking_pb2.BookingResponse(
            booking_id=booking_id,
            user_id=request.user_id,
            hotel_id=request.hotel_id,
            room_type=request.room_type,
            check_in=request.check_in,
            check_out=request.check_out,
            price=request.price,
            status="CONFIRMED",
            created_at=created_at,
        )

    def GetBooking(self, request, context):
        if not request.booking_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "booking_id is required")
            return None

        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "SELECT id, user_id, hotel_id, room_type, check_in, check_out, price, status, created_at FROM bookings WHERE id = %s",
                (request.booking_id,),
            )
            row = cur.fetchone()
            cur.close()
            conn.close()
        except Exception as e:
            context.abort(grpc.StatusCode.INTERNAL, f"Database error: {e}")

        if not row:
            context.abort(grpc.StatusCode.NOT_FOUND, f"Booking {request.booking_id} not found")
            return None

        return booking_pb2.BookingResponse(
            booking_id=row[0],
            user_id=row[1],
            hotel_id=row[2],
            room_type=row[3],
            check_in=str(row[4]),
            check_out=str(row[5]),
            price=float(row[6]),
            status=row[7],
            created_at=str(row[8]),
        )

    def CancelBooking(self, request, context):
        if not request.booking_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "booking_id is required")
            return None

        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT status FROM bookings WHERE id = %s", (request.booking_id,))
            row = cur.fetchone()
            cur.close()
            conn.close()
        except Exception as e:
            context.abort(grpc.StatusCode.INTERNAL, f"Database error: {e}")
            return None

        # Проверки ПОСЛЕ закрытия соединения — вне try блока
        if not row:
            context.abort(grpc.StatusCode.NOT_FOUND, f"Booking {request.booking_id} not found")
            return None

        if row[0] == "CANCELLED":
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Booking is already cancelled")
            return None

        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "UPDATE bookings SET status = 'CANCELLED' WHERE id = %s",
                (request.booking_id,),
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            context.abort(grpc.StatusCode.INTERNAL, f"Database error: {e}")
            return None

        publish_event("booking.cancelled", {
            "booking_id": request.booking_id,
            "reason": request.reason,
        })

        return booking_pb2.CancelBookingResponse(
            booking_id=request.booking_id,
            status="CANCELLED",
            message="Booking successfully cancelled",
        )

    def ListBookings(self, request, context):
        if not request.user_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "user_id is required")

        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "SELECT id, user_id, hotel_id, room_type, check_in, check_out, price, status, created_at FROM bookings WHERE user_id = %s ORDER BY created_at DESC",
                (request.user_id,),
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()
        except Exception as e:
            context.abort(grpc.StatusCode.INTERNAL, f"Database error: {e}")

        bookings = [
            booking_pb2.BookingResponse(
                booking_id=row[0],
                user_id=row[1],
                hotel_id=row[2],
                room_type=row[3],
                check_in=str(row[4]),
                check_out=str(row[5]),
                price=float(row[6]),
                status=row[7],
                created_at=str(row[8]),
            )
            for row in rows
        ]

        return booking_pb2.ListBookingsResponse(bookings=bookings)


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    booking_pb2_grpc.add_BookingServiceServicer_to_server(BookingServicer(), server)
    server.add_insecure_port("[::]:50051")
    print("gRPC server started on port 50051")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
