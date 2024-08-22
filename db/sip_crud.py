import logging
import sys

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models import Sip

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])


def get_sip(db: Session, uuid: str):
    return db.query(Sip).filter(Sip.uuid == uuid).first()


def invalid_sips(db: Session):
    return db.query(Sip.uuid, Sip.active).all()


def create_sip(db: Session, **sip_data):
    db_gate = Sip(**sip_data)
    try:
        db.add(db_gate)
        db.commit()
        db.refresh(db_gate)
        logging.info("Sip created successfully.")
        return db_gate
    except IntegrityError:
        db.rollback()  # Rollback the transaction to avoid any potential issues
        # Retrieve the existing sip if it already exists
        existing_sip = db.query(Sip).filter_by(uuid=sip_data.get('uuid')).first()
        if existing_sip:
            logging.warning("Sip already exists, updating with new data.")
            for key, value in sip_data.items():
                setattr(existing_sip, key, value)
            return update_sip(db=db, sip=existing_sip)
        else:
            logging.error("Failed to create or find the existing sip.")
            return None


def delete_sip(db: Session, sip: Sip):
    try:
        db.delete(sip)
        db.commit()
        return sip
    except:
        db.rollback()  # Rollback the transaction to avoid any potential issues
        logging.warning("Sip can't delete.")


def update_sip(db: Session, sip: Sip):
    try:
        db.commit()
        db.refresh(sip)
        logging.info("Sip updated successfully.")
        return sip
    except IntegrityError:
        db.rollback()  # Rollback the transaction to avoid any potential issues
        logging.error("Error updating Sip.")
        return get_sip(db, sip.uuid)
