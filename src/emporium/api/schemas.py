from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    customer_id: int
    model: str | None = None


class CustomerInfo(BaseModel):
    id: int
    name: str


class CreateSessionResponse(BaseModel):
    session_id: str
    customer: CustomerInfo


class MessageRequest(BaseModel):
    content: str
    debug: bool = False
    reasoning: bool | None = None


class ModelInfo(BaseModel):
    id: str
    label: str
    supports_reasoning: bool = False


class ConfigResponse(BaseModel):
    models: list[ModelInfo]
    default_model: str
