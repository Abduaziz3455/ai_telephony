from typing import List, Optional

from pydantic import BaseModel, constr


class ChannelCreate(BaseModel):
    uuid: str
    name: str = "gateway_name"
    endpoint: str = '192.168.1.0'
    username: str = '781131202'
    password: str = 'password'
    channelCount: int = 1


class CallInput(BaseModel):
    callUUID: str = '00000000-0000-0000-0000-000000000000'
    phone: constr(strip_whitespace=True, pattern=r'^(\d{9})$') = '907303455'

    class Config:
        from_attributes = True


class CampaignInput(BaseModel):
    uuid: str = '00000000-0000-0000-0000-000000000000'
    name: str = 'uysot Reklamasi'
    targets: List[CallInput]
    audio: str = 'https://storage.yandexcloud.net/myaudios/azizzzz.wav'
    retryCount: int = 1
    channels: List[str]
    channelCount: int = 1

    class Config:
        from_attributes = True


class CallCreate(BaseModel):
    uuid: str = '00000000-0000-0000-0000-000000000000'
    callUUID: str = '00000000-0000-0000-0000-000000000000'
    gateway_id: int
    campaign_uuid: int
    phone: str
    status: str = 'PENDING'
    startDate: str


class CampaignUpdate(BaseModel):
    uuid: str
    status: str = 'IN_PROGRESS'
    startDate: str = None
    endDate: str = None


class ChannelStatus(BaseModel):
    uuid: str
    active: bool = False


class CallUpdate(BaseModel):
    duration: int = None
    audio: str = None
    startDate: str
    campaignUUID: str = '00000000-0000-0000-0000-000000000000'
    channelUUID: str = '00000000-0000-0000-0000-000000000000'
    status: str = 'COMPLETED'
    callUUID: str = '00000000-0000-0000-0000-000000000000'


class CampaignCountResponse(BaseModel):
    campaign_count: int
    call_count: int


class ActiveCampaignResponse(BaseModel):
    uuid: str
    total_calls: int
    completed_time: Optional[int]
    remaining_time: Optional[int]
    time_since_started: Optional[int]
