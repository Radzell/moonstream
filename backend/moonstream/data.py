"""
Pydantic schemas for the Moonstream HTTP API
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class SubscriptionTypeResourceData(BaseModel):
    id: str
    name: str
    description: str
    stripe_product_id: Optional[str] = None
    stripe_price_id: Optional[str] = None
    active: bool = False


class SubscriptionTypesListResponce(BaseModel):
    subscription_types: List[SubscriptionTypeResourceData] = Field(default_factory=list)


class SubscriptionResourceData(BaseModel):
    id: str
    address: str
    color: str
    label: str
    user_id: str
    subscription_type_id: str


class CreateSubscriptionRequest(BaseModel):
    address: str
    color: str
    label: str
    subscription_type_id: str


class PingResponse(BaseModel):
    """
    Schema for ping response
    """

    status: str


class VersionResponse(BaseModel):
    """
    Schema for responses on /version endpoint
    """

    version: str


class SubscriptionRequest(BaseModel):
    """
    Schema for data retrieving from frontend about subscription.
    """

    blockchain: str


class SubscriptionResponse(BaseModel):
    """
    User subscription storing in Bugout resources.
    """

    user_id: str
    blockchain: str


class SubscriptionsListResponse(BaseModel):
    subscriptions: List[SubscriptionResourceData] = Field(default_factory=list)


class EVMFunctionSignature(BaseModel):
    type = "function"
    hex_signature: str
    text_signature_candidates: List[str] = Field(default_factory=list)


class EVMEventSignature(BaseModel):
    type = "event"
    hex_signature: str
    text_signature_candidates: List[str] = Field(default_factory=list)


class ContractABI(BaseModel):
    functions: List[EVMFunctionSignature]
    events: List[EVMEventSignature]


class EthereumTransaction(BaseModel):
    gas: int
    gasPrice: int
    value: int
    from_address: str
    to_address: Optional[str]
    hash: Optional[str] = None
    block_hash: Optional[str] = Field(default=None, alias="blockHash")
    block_number: Optional[int] = Field(default=None, alias="blockNumber")
    input: Optional[str] = None
    nonce: Optional[int] = None
    r: Optional[str] = None
    s: Optional[str] = None
    v: Optional[str] = None
    transaction_index: Optional[int] = Field(default=None, alias="transactionIndex")
    transaction_type: str = Field(default="0x0", alias="type")


class EthereumTransactionItem(BaseModel):
    color: Optional[str]
    from_label: Optional[str] = None
    to_label: Optional[str] = None
    block_number: Optional[int] = None
    gas: int
    gasPrice: int
    value: int
    nonce: Optional[str]
    from_address: Optional[str]  # = Field(alias="from")
    to_address: Optional[str]  # = Field(default=None, alias="to")
    hash: Optional[str] = None
    input: Optional[str] = None
    timestamp: Optional[int] = None
    subscription_type_id: Optional[str] = None


class StreamBoundary(BaseModel):
    """
    StreamBoundary represents a window of time through which an API caller can view a stream.

    This data structure is foundational to our stream rendering, and is used throughout the code
    base.
    """

    start_time: int
    end_time: int
    include_start: bool = False
    include_end: bool = False


class PageBoundary(StreamBoundary):
    """
    A PageBoundary adds information about previous and subsequent events to a StreamBoundary.

    This additional information helps callers manage their views into a stream.
    """

    next_event_time: Optional[int] = None
    previous_event_time: Optional[int] = None


class EthereumTransactionResponse(BaseModel):
    stream: List[EthereumTransactionItem]
    boundaries: Optional[PageBoundary]


class TxinfoEthereumBlockchainRequest(BaseModel):
    tx: EthereumTransaction


class TxinfoEthereumBlockchainResponse(BaseModel):
    tx: EthereumTransaction
    is_smart_contract_deployment: bool = False
    is_smart_contract_call: bool = False
    smart_contract_address: Optional[str] = None
    abi: Optional[ContractABI] = None
    errors: List[str] = Field(default_factory=list)
