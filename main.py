import logging
import os
import sys

from environs import Env
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

from apis.base import api_router
from apis.route_chat import validation_exception_handler
from core.config import settings
from db.base_class import Base
from db.session import engine

env = Env()
env.read_env()

os.environ['TZ'] = 'Asia/Tashkent'
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])


def create_tables():
    Base.metadata.create_all(bind=engine)


def include_router(app):
    app.include_router(api_router)


def start_application():
    foo_app = FastAPI(title=settings.PROJECT_NAME, description="Endpoints for robot calling", docs_url='/',
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
