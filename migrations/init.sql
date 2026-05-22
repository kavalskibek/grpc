CREATE TABLE IF NOT EXISTS bookings (
    id          VARCHAR(36) PRIMARY KEY,
    user_id     VARCHAR(36) NOT NULL,
    hotel_id    VARCHAR(36) NOT NULL,
    room_type   VARCHAR(50),
    check_in    DATE NOT NULL,
    check_out   DATE NOT NULL,
    price       DECIMAL(10, 2) NOT NULL,
    status      VARCHAR(20) NOT NULL DEFAULT 'CONFIRMED',
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bookings_user_id ON bookings(user_id);
CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status);
