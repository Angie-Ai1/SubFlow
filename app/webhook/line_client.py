from linebot.v3.messaging import ApiClient, Configuration, MessagingApi
from linebot.v3.webhook import WebhookParser

from app.config import settings

parser = WebhookParser(settings.line_channel_secret)

_messaging_config = Configuration(access_token=settings.line_channel_access_token)


def get_messaging_api() -> MessagingApi:
    return MessagingApi(ApiClient(_messaging_config))
