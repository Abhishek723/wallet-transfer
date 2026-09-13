from dataclasses import dataclass
from uuid import UUID, uuid4

from wallet_service.config import MAX_PAISE, Settings
from wallet_service.models import DomainError, TransferRequest


def transfer_response(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "from": str(row["from_wallet"]),
        "to": str(row["to_wallet"]),
        "amount_paise": row["amount_paise"],
        "status": row["status"],
        "reason": row["reason"],
        "created_at": row["created_at"].isoformat(),
    }


@dataclass
class TransferOutcome:
    body: dict
    replay: bool


class WalletService:
    def __init__(self, pool, settings: Settings):
        self.pool = pool
        self.settings = settings

    def get_or_create_wallet(self, user_id: UUID):
        with self.pool.connection() as conn, conn.transaction():
            conn.execute(
                "INSERT INTO wallets (id, user_id) VALUES (%s, %s) "
                "ON CONFLICT (user_id) DO NOTHING",
                (uuid4(), user_id),
            )
            # A separate statement sees the committed winner at READ COMMITTED.
            row = conn.execute(
                "SELECT id, balance_paise FROM wallets WHERE user_id = %s", (user_id,)
            ).fetchone()
        return row

    def get_wallet(self, wallet_id: UUID, user_id: UUID):
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT id, balance_paise FROM wallets WHERE id = %s AND user_id = %s",
                (wallet_id, user_id),
            ).fetchone()
        if not row:
            raise DomainError(404, "wallet_not_found", "Wallet not found")
        return row

    def get_transfer(self, transfer_id: UUID, user_id: UUID):
        with self.pool.connection() as conn:
            row = conn.execute(
                """SELECT t.* FROM transfers t
                JOIN wallets recipient ON recipient.id = t.to_wallet
                WHERE t.id = %s AND (t.user_id = %s OR recipient.user_id = %s)""",
                (transfer_id, user_id, user_id),
            ).fetchone()
        if not row:
            raise DomainError(404, "transfer_not_found", "Transfer not found")
        return transfer_response(row)

    def transfer(self, user_id: UUID, request: TransferRequest) -> TransferOutcome:
        with self.pool.connection() as conn, conn.transaction():
            conn.execute(
                "SELECT set_config('lock_timeout', %s, true)",
                (f"{self.settings.lock_timeout_ms}ms",),
            )
            conn.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                (f"{self.settings.statement_timeout_ms}ms",),
            )
            existing = conn.execute(
                "SELECT * FROM transfers WHERE user_id = %s AND idempotency_key = %s",
                (user_id, request.idempotency_key),
            ).fetchone()
            if existing:
                return self._replay(existing, request)
            sender = conn.execute(
                "SELECT user_id FROM wallets WHERE id = %s", (request.from_wallet,)
            ).fetchone()
            if not sender:
                raise DomainError(404, "wallet_not_found", "Sender wallet not found")
            if sender["user_id"] != user_id:
                raise DomainError(403, "forbidden", "You must own the sender wallet")
            if not conn.execute(
                "SELECT id FROM wallets WHERE id = %s", (request.to_wallet,)
            ).fetchone():
                raise DomainError(404, "wallet_not_found", "Recipient wallet not found")
            inserted = conn.execute(
                """INSERT INTO transfers
                (id, user_id, from_wallet, to_wallet, amount_paise, idempotency_key, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'pending')
                ON CONFLICT (user_id, idempotency_key) DO NOTHING RETURNING id""",
                (
                    uuid4(),
                    user_id,
                    request.from_wallet,
                    request.to_wallet,
                    request.amount_paise,
                    request.idempotency_key,
                ),
            ).fetchone()
            if not inserted:
                existing = conn.execute(
                    "SELECT * FROM transfers WHERE user_id = %s AND idempotency_key = %s",
                    (user_id, request.idempotency_key),
                ).fetchone()
                return self._replay(existing, request)

            # NO KEY UPDATE coexists with FK key-share locks taken by transfer inserts.
            # Explicitly lock one row at a time in the same order for every direction.
            balances = {}
            for wallet_id in sorted((request.from_wallet, request.to_wallet)):
                row = conn.execute(
                    "SELECT balance_paise FROM wallets WHERE id = %s FOR NO KEY UPDATE",
                    (wallet_id,),
                ).fetchone()
                balances[wallet_id] = row["balance_paise"]
            reason = None
            if balances[request.from_wallet] < request.amount_paise:
                reason = "insufficient_funds"
            elif balances[request.to_wallet] > MAX_PAISE - request.amount_paise:
                reason = "balance_limit_exceeded"
            else:
                conn.execute(
                    "UPDATE wallets SET balance_paise = balance_paise - %s WHERE id = %s",
                    (request.amount_paise, request.from_wallet),
                )
                conn.execute(
                    "UPDATE wallets SET balance_paise = balance_paise + %s WHERE id = %s",
                    (request.amount_paise, request.to_wallet),
                )
            row = conn.execute(
                "UPDATE transfers SET status = %s, reason = %s WHERE id = %s RETURNING *",
                ("declined" if reason else "succeeded", reason, inserted["id"]),
            ).fetchone()
        # No success escapes the method until the context manager commits.
        return TransferOutcome(transfer_response(row), False)

    @staticmethod
    def _replay(row: dict, request: TransferRequest):
        if (row["from_wallet"], row["to_wallet"], row["amount_paise"]) != (
            request.from_wallet,
            request.to_wallet,
            request.amount_paise,
        ):
            raise DomainError(409, "idempotency_conflict", "Key already used for another transfer")
        return TransferOutcome(transfer_response(row), True)
