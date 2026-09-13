CREATE TABLE users (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    token_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE wallets (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL UNIQUE REFERENCES users(id),
    balance_paise BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT valid_balance CHECK (balance_paise BETWEEN 0 AND 9007199254740991)
);

CREATE TABLE transfers (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    from_wallet UUID NOT NULL REFERENCES wallets(id),
    to_wallet UUID NOT NULL REFERENCES wallets(id),
    amount_paise BIGINT NOT NULL CHECK (amount_paise BETWEEN 1 AND 9007199254740991),
    idempotency_key VARCHAR(128) NOT NULL CHECK (length(idempotency_key) >= 1),
    status TEXT NOT NULL CHECK (status IN ('pending', 'succeeded', 'declined')),
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, idempotency_key),
    CHECK (from_wallet <> to_wallet),
    CHECK ((status = 'declined' AND reason IN ('insufficient_funds', 'balance_limit_exceeded'))
        OR (status IN ('pending', 'succeeded') AND reason IS NULL))
);
CREATE INDEX transfers_sender_idx ON transfers(from_wallet);
CREATE INDEX transfers_recipient_idx ON transfers(to_wallet);
