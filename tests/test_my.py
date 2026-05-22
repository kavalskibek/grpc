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


