#!/bin/bash
# Run this once before tests to generate Python gRPC code from .proto file

mkdir -p generated

python -m grpc_tools.protoc \
    -I./proto \
    --python_out=./generated \
    --grpc_python_out=./generated \
    ./proto/booking.proto

echo "Proto files generated in ./generated/"
echo "Files:"
ls generated/
