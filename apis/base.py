from fastapi import APIRouter

from apis.v1 import route_chat

api_router = APIRouter()
api_router.include_router(route_chat.router, prefix="", tags=[""])
