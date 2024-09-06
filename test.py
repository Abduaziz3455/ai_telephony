import random
from datetime import timedelta

from faker import Faker
from sqlalchemy.orm import Session

from db.models import Sip, CampaignStatus, Campaign, CallHistory, CallStatus

fake = Faker()


def create_fake_gateway():
    return Sip(uuid=fake.uuid4(), name=fake.company(), endpoint=fake.url(), username=fake.user_name(),
               password=fake.password(), channelCount=random.randint(1, 10), active=fake.boolean(),
               created_at=fake.date_time_this_year())


def create_fake_campaign(gateway_uuid):
    status = random.choice(list(CampaignStatus))
    start_date = fake.date_time_this_year()
    end_date = start_date + timedelta(days=random.randint(1, 30)) if status in [CampaignStatus.FINISHED,
                                                                                CampaignStatus.CANCELLED] else None
    return Campaign(uuid=fake.uuid4(), name=fake.catch_phrase(), audio=fake.file_path(extension='mp3'),
                    retryCount=random.randint(0, 5), status=status, startDate=start_date, endDate=end_date,
                    channelCount=random.randint(1, 5), gateway_uuid=gateway_uuid,
                    audio_duration=random.randint(1, 600))


def create_fake_callhistory(campaign_uuid, sip_id):
    status = random.choice(list(CallStatus))
    start_date = fake.date_time_this_year()
    duration = random.randint(1, 600) if status == CallStatus.COMPLETED else None
    return CallHistory(uuid=fake.uuid4(), sip_id=sip_id, campaign_uuid=campaign_uuid, phone=fake.phone_number(),
                       status=status,
                       recording=fake.file_path(extension='wav') if status == CallStatus.COMPLETED else None,
                       duration=duration, startDate=start_date)


def add_fake_data(session: Session, num_gateways=5, num_campaigns_per_gateway=10, num_calls_per_campaign=50):
    for _ in range(num_gateways):
        gateway = create_fake_gateway()
        session.add(gateway)
        session.flush()  # Ensure the gateway.id is available

        for _ in range(num_campaigns_per_gateway):
            campaign = create_fake_campaign(gateway.uuid)
            session.add(campaign)
            session.flush()  # Ensure the campaign.uuid is available

            for _ in range(num_calls_per_campaign):
                call_history = create_fake_callhistory(campaign.uuid, gateway.id)
                session.add(call_history)

    session.commit()


import pandas as pd
from sqlalchemy import create_engine

# Define your PostgreSQL database credentials
DB_USER = 'postgres'
DB_PASSWORD = 'abdu3421'
DB_HOST = '127.0.0.1'
DB_PORT = '5432'
DB_NAME = 'robot_call'

# Create a connection to the PostgreSQL database
engine = create_engine(f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}')

# Load CSV data into a DataFrame
df = pd.read_csv('script.csv')

# Define the table name where data will be inserted
table_name = 'script'

# Insert data into the PostgreSQL table
df.to_sql(table_name, engine, if_exists='append', index=False)

print(f'Data successfully inserted into table {table_name}')
