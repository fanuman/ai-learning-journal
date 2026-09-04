from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str
    total_cost: float

class ChatMetaData(BaseModel):
    total_calls: int
    total_retries: int
    total_cost: float

class ChatMessage(BaseModel):
    role: str
    content: str

class StreamChatRequest(BaseModel):
    messages: list[ChatMessage]