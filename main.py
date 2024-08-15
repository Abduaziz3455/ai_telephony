import asyncio
import logging
import os
import sys

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from environs import Env
from fastapi import FastAPI, BackgroundTasks
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

from apis.base import api_router
from apis.v1.route_chat import validation_exception_handler, retry_main_call
from core.config import settings
from db.base_class import Base
from db.campaign_crud import init_status
from db.session import engine, get_db
from pika_client import PikaClient
from schemas.input_query import ChannelStatus
from script import continue_campaign, check_gateway, send_campaign_update

env = Env()
env.read_env()

os.environ['TZ'] = 'Asia/Tashkent'
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])


def create_tables():
    Base.metadata.create_all(bind=engine)


def include_router(app):
    app.include_router(api_router)


def log_incoming_message(cls, message: dict):
    """Method to do something meaningful with the incoming message"""
    logging.info('Here we got incoming message %s', message)


pika_client = PikaClient(log_incoming_message, env.str("SIP_QUEUE"))


async def send_channel_status(channel: ChannelStatus):
    await pika_client.send_message(channel.dict())


class FooApp(FastAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


def start_application():
    foo_app = FooApp(title=settings.PROJECT_NAME, description="Endpoints for robot calling", docs_url='/',
                     version=settings.PROJECT_VERSION)
    foo_app.add_exception_handler(RequestValidationError, validation_exception_handler)
    try:
        foo_app.mount("/recordings", StaticFiles(directory=env.str("RECORD_LOC")), name="recordings")
    except Exception as e:
        try:
            if not os.path.exists(env.str("RECORD_LOC")):
                os.makedirs(env.str("RECORD_LOC"))
                foo_app.mount("/recordings", StaticFiles(directory=env.str("RECORD_LOC")), name="recordings")
        except Exception as e:
            logging.error(e)

    create_tables()
    include_router(foo_app)
    return foo_app


app = start_application()
scheduler = AsyncIOScheduler()


async def check_status(db):
    logging.info("Checking sip statuses...")
    sips = await check_gateway(db)
    if sips:
        tasks = []
        for uuid, active in sips:
            message = ChannelStatus(uuid=uuid, active=active)
            tasks.append(asyncio.create_task(send_channel_status(message)))
        await asyncio.gather(*tasks)
        logging.info("Sending statuses...")
    else:
        logging.info("No false sips available")


@app.on_event('startup')
async def startup():
    db = next(get_db())
    init_status(db)
    loop = asyncio.get_event_loop()
    scheduler.add_job(lambda: loop.create_task(check_status(db)), 'interval', minutes=10, max_instances=15)
    scheduler.start()
    background_tasks = BackgroundTasks()
    background_tasks.add_task(continue_campaign, db, send_campaign_update, retry_main_call, start=True)


@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown()
