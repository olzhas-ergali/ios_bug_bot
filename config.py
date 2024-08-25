from environs import Env


class Environ:
    def __init__(self):
        env = Env()
        env.read_env(".env")
        self.host = env.str("DB_HOST")
        self.port = env.str("DB_PORT")
        self.user = env.str("DB_USER")
        self.password = env.str("DB_PASSWORD")
        self.dbname = env.str("DB_NAME")
        self.bot_token = env.str("BOT_TOKEN")
        self.logging_level = env.int("LOGGING_LEVEL")
        self.dev_mode = env.bool("DEV_MODE")
        self.admins = env.str("ADMINS").split(",")
        self.channel_id = env.str("CHANNEL_ID")

    def psycopg_url(self):
        return f"postgresql+psycopg2://{self.user}:{self.password}@{self.host}:{self.port}/{self.dbname}"

    def asyncpg_url(self):
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.dbname}"
