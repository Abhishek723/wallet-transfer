from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wallet_service.config import MAX_PAISE


class TransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_wallet: UUID = Field(alias="from")
    to_wallet: UUID = Field(alias="to")
    amount_paise: Annotated[int, Field(strict=True, gt=0, le=MAX_PAISE)]
    idempotency_key: Annotated[
        str, Field(strict=True, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    ]

    @model_validator(mode="after")
    def different_wallets(self):
        if self.from_wallet == self.to_wallet:
            raise ValueError("Sender and recipient must be different wallets")
        return self


class WalletResponse(BaseModel):
    id: UUID
    balance_paise: int


class TransferResponse(BaseModel):
    id: UUID
    from_wallet: UUID = Field(alias="from")
    to_wallet: UUID = Field(alias="to")
    amount_paise: int
    status: Literal["succeeded", "declined"]
    reason: str | None
    created_at: str


class DomainError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message
        super().__init__(message)
