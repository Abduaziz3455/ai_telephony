from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, Column, Integer, String, Enum as SqlEnum, DateTime, ForeignKey

from db.base_class import Base


class CampaignStatus(Enum):
    PENDING = "PENDING"
    BUSY = "BUSY"
    IN_PROGRESS = "IN_PROGRESS"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    FINISHED = "FINISHED"
    ERROR_OCCURRED = "ERROR_OCCURRED"


class CallStatus(Enum):
    PENDING = "PENDING"  # will be active soon
    RINGING = "RINGING"  # call going on
    MISSED = "MISSED"  # not answered
    TERMINATED = "TERMINATED"  # answered but interrupted by user
    DROPPED = "DROPPED"  # answered but interrupted by server
    COMPLETED = "COMPLETED"  # answered and listened to the end
    CANCELLED = "CANCELLED"


class Gateway(Base):
    id = Column(Integer, primary_key=True)
    uuid = Column(String, unique=True, nullable=False, index=True)
    name = Column(String)
    endpoint = Column(String)
    username = Column(String)
    password = Column(String)
    channelCount = Column(Integer)
    active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now())


class CallHistory(Base):
    id = Column(Integer, primary_key=True)
    uuid = Column(String, unique=True)
    gateway_id = Column(Integer, ForeignKey('gateway.id'))
    campaign_uuid = Column(String, ForeignKey('campaign.uuid'))
    phone = Column(String)
    status = Column(SqlEnum(CallStatus), nullable=False, default=CallStatus.RINGING)
    recording = Column(String, nullable=True)
    duration = Column(Integer, nullable=True)
    startDate = Column(DateTime(), default=datetime.now())


class Campaign(Base):
    id = Column(Integer, primary_key=True)
    uuid = Column(String, unique=True)
    name = Column(String)
    audio = Column(String)
    audio_duration = Column(Integer, nullable=True)
    retryCount = Column(Integer, default=0)
    status = Column(SqlEnum(CampaignStatus), nullable=False, default=CampaignStatus.PENDING)
    startDate = Column(DateTime(), nullable=True)
    endDate = Column(DateTime(), nullable=True)
    channelCount = Column(Integer, nullable=False)
    gateway_uuid = Column(String, ForeignKey('gateway.uuid'))


class Status(Base):
    id = Column(Integer, primary_key=True)
    reloadStatus = Column(Boolean, default=False)
    call_active = Column(Boolean, default=False)
    call_active_b = Column(Boolean, default=False)
