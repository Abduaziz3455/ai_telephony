from environs import Env

env = Env()
env.read_env()


class Settings:
    PROJECT_NAME: str = "Robot Caller"
    PROJECT_VERSION: str = "0.0.1"
    DATABASE_URL = f"postgresql://{env.str('DB_USER')}:{env.str('DB_PASS')}@{env.str('DB_HOST')}/{env.str('DB_NAME')}"


settings = Settings()
