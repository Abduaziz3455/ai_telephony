import logging
import sys

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models import Campaign
from db.sip_crud import get_sip
from schemas.input_query import GetCampaign

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])


def get_campaign(db: Session, uuid: str):
    return db.query(Campaign).filter(Campaign.uuid == uuid).first()


def get_campaigns(db: Session, active=False):
    if active:
        camps = db.query(Campaign).filter(Campaign.status.in_(['PENDING', 'IN_PROGRESS'])).all()
    else:
        camps = db.query(Campaign).filter(Campaign.status.notin_(['PENDING', 'IN_PROGRESS'])).all()
    return [GetCampaign(id=camp.id, name=camp.name, audio_duration=camp.audio_duration, retryCount=camp.retryCount,
                        sip_name=get_sip(db, camp.sip_uuid).name, channelCount=camp.channelCount, status=camp.status,
                        startDate=camp.startDate.strftime("%d.%m.%Y %H:%M"),
                        endDate=camp.endDate.strftime("%d.%m.%Y %H:%M")) for camp in camps]


def create_campaign(db: Session, uuid: str, name: str, audio: str, channelCount: int, sip_uuid: str, duration: int = None,
                    retryCount: int = 0):
    db_camp = Campaign(uuid=uuid, name=name, audio=audio, retryCount=retryCount, channelCount=channelCount,
                       sip_uuid=sip_uuid, audio_duration=duration)
    try:
        db.add(db_camp)
        db.commit()
        db.refresh(db_camp)
        logging.info("Campaign created successfully.")
        return db_camp
    except IntegrityError:
        db.rollback()  # Rollback the transaction to avoid any potential issues
        logging.warning("Campaign already exists.")
        return get_campaign(db, uuid)  # Or return None or handle as needed


def update_campaign(db: Session, campaign: Campaign, status: str = None, endDate: str = None):
    if status:
        campaign.status = status
    if endDate:
        campaign.endDate = endDate

    try:
        db.commit()
        db.refresh(campaign)
        logging.info("Campaign updated successfully.")
        return campaign
    except IntegrityError:
        db.rollback()  # Rollback the transaction to avoid any potential issues
        logging.error("Error updating campaign.")
        return None
