import random
from datetime import timedelta

from faker import Faker
from sqlalchemy.orm import Session

from db.models import Sip, CampaignStatus, Campaign, CallHistory, CallStatus, Script
from db.session import get_db

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


data = [
    {
        "id": 0,
        "text": "Men to'liq summani [sana] to'layman. Mijoz to'lovni belgilangan sana bo'yicha to'liq amalga oshirishini bildiradi. To'liq to'lov, to'lash vaqti. To'lov. to'liq, to'lash, sana",
        "voice": "path/to/voice/file0.wav"  # Adjust this with the actual voice file path if needed
    },
    {
        "id": 1,
        "text": "To'lov rejasini tuzishim mumkinmi? Mijoz to'lov rejasini tuzish imkoniyatini so'raydi. To'lov rejasi, bo'lib-bo'lib to'lash. To'lov. to'lov, rejasi, tuzish",
        "voice": "path/to/voice/file1.wav"
    },
    {
        "id": 2,
        "text": "Men allaqachon to'laganman. Mijoz allaqachon to'lovni amalga oshirganini ta'kidlaydi. To'langan, amalga oshirilgan to'lov. To'lov. to'langan, allaqachon",
        "voice": "path/to/voice/file2.wav"
    },
    {
        "id": 3,
        "text": "Hozir gaplasha olmayman, qayta qo'ng'iroq qila olasizmi? Mijoz hozirda gaplasha olmasligini va keyinroq qo'ng'iroq qilishni so'raydi. Qayta qo'ng'iroq qilish, gaplasha olmayman. Qo'ng'iroq. gaplasha olmayman, qayta qo'ng'iroq",
        "voice": "path/to/voice/file3.wav"
    },
    {
        "id": 4,
        "text": "Men hech qanday hisob-faktura olmadim. Mijoz hisob-faktura olmaganini bildiradi. Hisob-faktura olmagan, yuborilmagan. Hisob-faktura. hisob-faktura, olmagan",
        "voice": "path/to/voice/file4.wav"
    },
    {
        "id": 5,
        "text": "Men to'lamayman. Mijoz qarzini to'lashni rad etadi. To'lamayman, rad etaman. Rad etish. to'lamayman, rad",
        "voice": "path/to/voice/file5.wav"
    },
    {
        "id": 6,
        "text": "Men moliyaviy qiyinchiliklardan o'tmoqdaman. Mijoz moliyaviy qiyinchiliklarga duch kelayotganini bildiradi. Moliyaviy qiyinchiliklar, qiyin ahvol. Moliyaviy qiyinchiliklar. moliyaviy, qiyinchiliklar",
        "voice": "path/to/voice/file6.wav"
    },
    {
        "id": 7,
        "text": "Qarz summasini va bank nomini qayta ayta olasizmi, iltimos? Mijoz qarz summasi va bank nomini qayta so'raydi. Qarz miqdori, bank nomi, takrorlash. Ma'lumot so'rash. qarz, miqdor, bank",
        "voice": "path/to/voice/file7.wav"
    },
    {
        "id": 8,
        "text": "Boshqa. Mijoz boshqa sabablarga ko'ra javob beradi. Boshqa sabablar, boshqa javoblar. Boshqa. boshqa, sabab",
        "voice": "path/to/voice/file8.wav"
    }
]


def main():
    db = next(get_db())
    try:
        for entry in data:
            script = Script(id=entry["id"], text=entry["text"], voice=entry["voice"])
            db.add(script)

        db.commit()
        print("Data inserted successfully!")
    finally:
        db.close()


if __name__ == "__main__":
    main()
