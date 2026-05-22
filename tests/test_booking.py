import grpc
import pytest
import allure
import booking_pb2
import booking_pb2_grpc





@allure.feature("Booking")
@allure.story("Create Booking")
class TestCreateBooking:


    def test_create_new_booking(self, booking_stub, booking_payload):

        payload = booking_payload()
        request = booking_pb2.CreateBookingRequest(**payload)

        response = booking_stub.CreateBooking(request)
        assert response.booking_id != ""
        assert response.user_id == payload["user_id"]


    @allure.title("Successfully create booking with valid data")
    def test_create_booking_success(self, booking_stub, booking_payload):
        payload = booking_payload()
        request = booking_pb2.CreateBookingRequest(**payload)

        response = booking_stub.CreateBooking(request)

        assert response.booking_id != ""
        assert response.user_id == payload["user_id"]
        assert response.hotel_id == payload["hotel_id"]
        assert response.room_type == payload["room_type"]
        assert response.price == payload["price"]
        assert response.status == "CONFIRMED"
        assert response.created_at != ""

    @allure.title("Booking appears in database after creation")
    def test_create_booking_persisted_in_db(self, booking_stub, booking_payload, db_cursor):
        """Critical: verify booking actually saved to DB, not just returned."""
        payload = booking_payload()
        request = booking_pb2.CreateBookingRequest(**payload)
        response = booking_stub.CreateBooking(request)

        db_cursor.execute(
            "SELECT id, status, price FROM bookings WHERE id = %s",
            (response.booking_id,)
        )
        row = db_cursor.fetchone()

        assert row is not None, "Booking not found in database"
        assert row[0] == response.booking_id
        assert row[1] == "CONFIRMED"
        assert float(row[2]) == payload["price"]

    @allure.title("booking.created event published to RabbitMQ")
    def test_create_booking_publishes_event(self, booking_stub, booking_payload, consume_event):
        """Critical: verify event published to message broker."""
        payload = booking_payload()
        request = booking_pb2.CreateBookingRequest(**payload)
        response = booking_stub.CreateBooking(request)

        event = consume_event("booking.created", timeout=5)

        assert event is not None, "No event published to RabbitMQ"
        assert event["booking_id"] == response.booking_id
        assert event["user_id"] == payload["user_id"]
        assert event["status"] == "CONFIRMED"

    @allure.title("Create booking fails without user_id")
    def test_create_booking_missing_user_id(self, booking_stub, booking_payload):
        payload = booking_payload(user_id="")
        request = booking_pb2.CreateBookingRequest(**payload)

        with pytest.raises(grpc.RpcError) as exc:
            booking_stub.CreateBooking(request)

        assert exc.value.code() == grpc.StatusCode.INVALID_ARGUMENT
        assert "user_id" in exc.value.details().lower()

    @allure.title("Create booking fails with zero price")
    def test_create_booking_zero_price(self, booking_stub, booking_payload):
        payload = booking_payload(price=0)
        request = booking_pb2.CreateBookingRequest(**payload)

        with pytest.raises(grpc.RpcError) as exc:
            booking_stub.CreateBooking(request)

        assert exc.value.code() == grpc.StatusCode.INVALID_ARGUMENT

    @allure.title("Create booking fails with negative price")
    def test_create_booking_negative_price(self, booking_stub, booking_payload):
        payload = booking_payload(price=-100)
        request = booking_pb2.CreateBookingRequest(**payload)

        with pytest.raises(grpc.RpcError) as exc:
            booking_stub.CreateBooking(request)

        assert exc.value.code() == grpc.StatusCode.INVALID_ARGUMENT

    @allure.title("Create booking fails without check_in date")
    def test_create_booking_missing_check_in(self, booking_stub, booking_payload):
        payload = booking_payload(check_in="")
        request = booking_pb2.CreateBookingRequest(**payload)

        with pytest.raises(grpc.RpcError) as exc:
            booking_stub.CreateBooking(request)

        assert exc.value.code() == grpc.StatusCode.INVALID_ARGUMENT


@allure.feature("Booking")
@allure.story("Get Booking")
class TestGetBooking:

    @allure.title("Get existing booking by ID")
    def test_get_booking_success(self, booking_stub, created_booking):
        request = booking_pb2.GetBookingRequest(booking_id=created_booking.booking_id)
        response = booking_stub.GetBooking(request)

        assert response.booking_id == created_booking.booking_id
        assert response.user_id == created_booking.user_id
        assert response.status == "CONFIRMED"

    @allure.title("Get booking fails for non-existent ID")
    def test_get_booking_not_found(self, booking_stub):
        request = booking_pb2.GetBookingRequest(booking_id="non-existent-id-12345")

        with pytest.raises(grpc.RpcError) as exc:
            booking_stub.GetBooking(request)

        assert exc.value.code() == grpc.StatusCode.NOT_FOUND

    @allure.title("Get booking fails with empty ID")
    def test_get_booking_empty_id(self, booking_stub):
        request = booking_pb2.GetBookingRequest(booking_id="")

        with pytest.raises(grpc.RpcError) as exc:
            booking_stub.GetBooking(request)

        assert exc.value.code() == grpc.StatusCode.INVALID_ARGUMENT


@allure.feature("Booking")
@allure.story("Cancel Booking")
class TestCancelBooking:

    @allure.title("Successfully cancel confirmed booking")
    def test_cancel_booking_success(self, booking_stub, created_booking):
        request = booking_pb2.CancelBookingRequest(
            booking_id=created_booking.booking_id,
            reason="Changed plans"
        )
        response = booking_stub.CancelBooking(request)

        assert response.booking_id == created_booking.booking_id
        assert response.status == "CANCELLED"

    @allure.title("Status updated to CANCELLED in database")
    def test_cancel_booking_updates_db(self, booking_stub, created_booking, db_cursor):
        booking_stub.CancelBooking(
            booking_pb2.CancelBookingRequest(
                booking_id=created_booking.booking_id,
                reason="Test cancel"
            )
        )

        db_cursor.execute(
            "SELECT status FROM bookings WHERE id = %s",
            (created_booking.booking_id,)
        )
        row = db_cursor.fetchone()

        assert row[0] == "CANCELLED"

    @allure.title("booking.cancelled event published to RabbitMQ")
    def test_cancel_booking_publishes_event(self, booking_stub, created_booking, consume_event):
        booking_stub.CancelBooking(
            booking_pb2.CancelBookingRequest(
                booking_id=created_booking.booking_id,
                reason="Test reason"
            )
        )

        event = consume_event("booking.cancelled", timeout=5)

        assert event is not None
        assert event["booking_id"] == created_booking.booking_id
        assert event["reason"] == "Test reason"

    @allure.title("Cannot cancel already cancelled booking")
    def test_cancel_already_cancelled_booking(self, booking_stub, created_booking):
        cancel_request = booking_pb2.CancelBookingRequest(
            booking_id=created_booking.booking_id,
            reason="First cancel"
        )
        booking_stub.CancelBooking(cancel_request)

        with pytest.raises(grpc.RpcError) as exc:
            booking_stub.CancelBooking(cancel_request)

        assert exc.value.code() == grpc.StatusCode.FAILED_PRECONDITION

    @allure.title("Cancel non-existent booking returns NOT_FOUND")
    def test_cancel_non_existent_booking(self, booking_stub):
        with pytest.raises(grpc.RpcError) as exc:
            booking_stub.CancelBooking(
                booking_pb2.CancelBookingRequest(
                    booking_id="does-not-exist",
                    reason="test"
                )
            )

        assert exc.value.code() == grpc.StatusCode.NOT_FOUND


@allure.feature("Booking")
@allure.story("List Bookings")
class TestListBookings:

    @allure.title("List bookings for user returns all bookings")
    def test_list_bookings_success(self, booking_stub, booking_payload):
        user_id = "test-user-list-123"
        # Create 3 bookings for same user
        for _ in range(3):
            booking_stub.CreateBooking(
                booking_pb2.CreateBookingRequest(**booking_payload(user_id=user_id))
            )

        response = booking_stub.ListBookings(
            booking_pb2.ListBookingsRequest(user_id=user_id)
        )

        assert len(response.bookings) >= 3
        assert all(b.user_id == user_id for b in response.bookings)

    @allure.title("List bookings for unknown user returns empty list")
    def test_list_bookings_empty_for_unknown_user(self, booking_stub):
        response = booking_stub.ListBookings(
            booking_pb2.ListBookingsRequest(user_id="unknown-user-xyz-999")
        )

        assert len(response.bookings) == 0

    @allure.title("List bookings fails with empty user_id")
    def test_list_bookings_empty_user_id(self, booking_stub):
        with pytest.raises(grpc.RpcError) as exc:
            booking_stub.ListBookings(
                booking_pb2.ListBookingsRequest(user_id="")
            )

        assert exc.value.code() == grpc.StatusCode.INVALID_ARGUMENT
