import grpc
import pytest
import allure
import booking_pb2
import booking_pb2_grpc

def test_create_new_booking( booking_stub, booking_payload):
    payload = booking_payload()
    request = booking_pb2.CreateBookingRequest(**payload)

    response = booking_stub.CreateBooking(request)
    assert response.booking_id != ""
    assert response.user_id == payload["user_id"]



def test_get_booking_by_id( booking_stub, booking_payload):
    payload = booking_payload()
    request = booking_pb2.CreateBookingRequest(**payload)

    response = booking_stub.CreateBooking(request)

    data = response.booking_id

    request2 = booking_pb2.GetBookingRequest(booking_id=data)
    response2 = booking_stub.GetBooking(request2)


    assert response2.booking_id == data
    assert response2.status == "CONFIRMED"


def test_cancel_created_booking(booking_stub, booking_payload):
    payload = booking_payload()
    request = booking_pb2.CreateBookingRequest(**payload)

    response = booking_stub.CreateBooking(request)

    data = response.booking_id

    request2 = booking_pb2.CancelBookingRequest(booking_id=data)
    response2 = booking_stub.CancelBooking(request2)
    assert response2.booking_id == data
    assert response2.status == "CANCELLED"



def test_check_failed_error( booking_stub, booking_payload):
    payload = booking_payload()
    request = booking_pb2.CreateBookingRequest(**payload)

    response = booking_stub.CreateBooking(request)

    data = response.booking_id

    request2 = booking_pb2.CancelBookingRequest(booking_id=data)
    response2 = booking_stub.CancelBooking(request2)
    assert response2.booking_id == data
    assert response2.status == "CANCELLED"

    with pytest.raises(grpc.RpcError) as exc:
        request3 = booking_pb2.CancelBookingRequest(booking_id=data)
        booking_stub.CancelBooking(request3)

    assert exc.value.code() == grpc.StatusCode.FAILED_PRECONDITION
