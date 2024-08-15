import logging
import sys

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models import Campaign, Status

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])


def get_campaign(db: Session, uuid: str):
    return db.query(Campaign).filter(Campaign.uuid == uuid).first()


def create_campaign(db: Session, uuid: str, name: str, audio: str, channelCount: int, gateway_uuid: str, duration: int = None,
                    retryCount: int = 0):
    db_camp = Campaign(uuid=uuid, name=name, audio=audio, retryCount=retryCount, channelCount=channelCount,
                       gateway_uuid=gateway_uuid, audio_duration=duration)
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


def get_status(db: Session):
    return db.query(Status).first()


def init_status(db):
    # Check if a Status record already exists
    status_record = db.query(Status).first()
    if status_record:
        # Update existing record
        status_record.reloadStatus = False
        status_record.call_active = False
    else:
        # Create new record
        status_record = Status()
        db.add(status_record)
    db.commit()


def update_status(db: Session, status: Status):
    try:
        db.commit()
        db.refresh(status)
        logging.info("Campaign updated successfully.")
        return status
    except IntegrityError:
        db.rollback()  # Rollback the transaction to avoid any potential issues
        logging.error("Error updating campaign.")
        return None
