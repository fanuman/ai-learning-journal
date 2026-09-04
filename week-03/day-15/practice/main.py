from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from production_wrapper import ProductionLLMClient
from fastapi import FastAPI, HTTPException
from models import ChatRequest, ChatResponse, ChatMetaData, StreamChatRequest
from fastapi.responses import StreamingResponse
from openai import OpenAI

from fastapi.middleware.cors import CORSMiddleware


llm_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global llm_client
    llm_client = ProductionLLMClient()
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # fine for local dev only — never do this in production
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    try:
        response = llm_client.chat([
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": request.message}
        ])

        return ChatResponse(
            reply=response.choices[0].message.content,
            total_cost=llm_client.total_cost
        )
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))

@app.get("/cost", response_model=ChatMetaData)
def cost():
    return ChatMetaData(
        total_calls=llm_client.total_calls,
        total_retries=llm_client.total_retries,
        total_cost=llm_client.total_cost
    )

@app.post("/chat/stream")
def chat_stream(request: StreamChatRequest):
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    return StreamingResponse(llm_client.stream_response(messages), media_type="text/event-stream")