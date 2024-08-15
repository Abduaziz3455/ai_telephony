import logging
import sys

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models import Gateway

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])


def get_gateway(db: Session, uuid: str):
    return db.query(Gateway).filter(Gateway.uuid == uuid).first()


def invalid_gateways(db: Session):
    return db.query(Gateway.uuid, Gateway.active).all()


def create_gateway(db: Session, **gateway_data):
    db_gate = Gateway(**gateway_data)
    try:
        db.add(db_gate)
        db.commit()
        db.refresh(db_gate)
        logging.info("Gateway created successfully.")
        return db_gate
    except IntegrityError:
        db.rollback()  # Rollback the transaction to avoid any potential issues
        # Retrieve the existing gateway if it already exists
        existing_gate = db.query(Gateway).filter_by(uuid=gateway_data.get('uuid')).first()
        if existing_gate:
            logging.warning("Gateway already exists, updating with new data.")
            for key, value in gateway_data.items():
                setattr(existing_gate, key, value)
            return update_gateway(db=db, gateway=existing_gate)
        else:
            logging.error("Failed to create or find the existing gateway.")
            return None


def delete_gateway(db: Session, gateway: Gateway):
    try:
        db.delete(gateway)
        db.commit()
        return gateway
    except:
        db.rollback()  # Rollback the transaction to avoid any potential issues
        logging.warning("Gateway can't delete.")


def update_gateway(db: Session, gateway: Gateway):
    try:
        db.commit()
        db.refresh(gateway)
        logging.info("Sip updated successfully.")
        return gateway
    except IntegrityError:
        db.rollback()  # Rollback the transaction to avoid any potential issues
        logging.error("Error updating Sip.")
        return get_gateway(db, gateway.uuid)
