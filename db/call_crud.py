import logging
import sys
import uuid
from typing import List

from sqlalchemy import and_, desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.campaign_crud import get_campaign
from db.models import CallHistory
from schemas.input_query import CallInput, GetCall

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])


def get_call(db: Session, uuid: str):
    return db.query(CallHistory).filter(CallHistory.uuid == uuid).first()


def create_call(db: Session, uuid: str, sip_id: int, campaign_uuid: str, phone: str):
    db_call = CallHistory(uuid=uuid, sip_id=sip_id, campaign_uuid=campaign_uuid, phone=phone)
    try:
        db.add(db_call)
        db.commit()
        db.refresh(db_call)
        logging.info("Call created successfully.")
        return db_call
    except IntegrityError:
        db.rollback()  # Rollback the transaction to avoid any potential issues
        logging.warning("Call already exists.")
        return get_call(db, uuid)  # Or return None or handle as needed


def bulk_create_call(db: Session, calls: List[CallHistory]):
    try:
        db.add_all(calls)
        db.commit()
        logging.info("Call created successfully.")
    except IntegrityError:
        db.rollback()  # Rollback the transaction to avoid any potential issues
        logging.warning("Call already exists.")


def update_call(db: Session, call: CallHistory, recording: str = None, duration: int = None):
    if recording:
        call.recording = recording
    if duration:
        call.duration = duration
    try:
        db.commit()
        db.refresh(call)
        logging.info("Call updated successfully.")
        return call
    except IntegrityError:
        db.rollback()  # Rollback the transaction to avoid any potential issues
        logging.error("Error updating Call.")
        return None


def cancel_calls(db: Session, campaign_uuid: str):
    try:
        # Fetch the call records for the given campaign UUID
        calls = db.query(CallHistory).filter(
            and_(CallHistory.campaign_uuid == campaign_uuid, CallHistory.status == 'PENDING')).all()

        # Update the status to CANCELLED
        for call in calls:
            call.status = 'CANCELLED'

        db.commit()

        return True
    except Exception as e:
        db.rollback()
        return False


def get_call_history(campaign_uuid: str, db: Session):
    query = db.query(CallHistory).filter(CallHistory.campaign_uuid == campaign_uuid).all()
    return [CallInput(callUUID=call.uuid, phone=call.phone) for call in query]


def get_target_calls(df):
    return [CallInput(callUUID=str(uuid.uuid4()), phone=call) for call in df['phone'].tolist()]


def get_calls(db: Session):
    query = db.query(CallHistory).order_by(desc(CallHistory.id)).all()
    calls = [GetCall(id=call.id, phone=call.phone,
                     campaignName=get_campaign(db, call.campaign_uuid).name,
                     status=call.status, recording=call.recording if call.recording else '', duration=call.duration if call.duration else 0,
                     startDate=call.startDate.strftime("%d.%m.%Y %H:%M") if call.startDate else '') for call in query]
    return calls
