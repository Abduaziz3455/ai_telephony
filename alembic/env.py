from alembic import context

#new
from core.config import settings
from db.base_class import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

#new
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata
