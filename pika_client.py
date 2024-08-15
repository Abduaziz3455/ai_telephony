import json
import logging
import sys
import uuid

import aio_pika
from environs import Env

env = Env()
env.read_env()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])


class PikaClient:
    def __init__(self, process_callable, publish_queue_name):
        self.publish_queue_name = publish_queue_name
        self.consume_queue_name = env.str('CONSUME_QUEUE', 'abduaziz')
        self.process_callable = process_callable
        self.connection = None
        self.channel = None
        logging.info('Pika connection initialized')

    async def connect(self):
        self.connection = await aio_pika.connect_robust(host=env.str('RABBIT_HOST', '127.0.0.1'),
                                                        password=env.str('RABBIT_PASS', '<PASSWORD>'))
        self.channel = await self.connection.channel()

        # Declare the publish queue as durable
        await self.channel.declare_queue(self.publish_queue_name, durable=True)

    async def consume(self, loop):
        """Setup message listener with the current running loop"""
        await self.connect()
        queue = await self.channel.declare_queue(self.consume_queue_name, durable=True)
        await queue.consume(self.process_incoming_message, no_ack=False)
        logging.info('Established pika async listener')

    async def send_message(self, message: dict):
        """Method to publish message to RabbitMQ"""
        if not self.channel:
            await self.connect()
        await self.channel.default_exchange.publish(
            aio_pika.Message(body=json.dumps(message).encode(), correlation_id=str(uuid.uuid4()),
                             reply_to=self.consume_queue_name), routing_key=self.publish_queue_name)

    async def process_incoming_message(self, message: aio_pika.IncomingMessage):
        """Processing incoming message from RabbitMQ"""
        async with message.process():
            body = message.body
            logging.info('Received message')
            if body:
                self.process_callable(json.loads(body))

    async def close(self):
        await self.channel.close()
