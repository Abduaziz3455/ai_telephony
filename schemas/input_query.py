from typing import List, Optional

from pydantic import BaseModel, constr


class SipCreate(BaseModel):
    name: str = "uztel"
    endpoint: str = '217.29.116.183'
    username: str = '781131202'
    password: str = 'password'
    channelCount: int = 1


class GetSip(BaseModel):
    uuid: str = "uztel"
    name: str = "uztel"
    endpoint: str = '217.29.116.183'
    username: str = '781131202'
    password: str = 'password'
    channelCount: int = 1


class SipWithoutPassword(BaseModel):
    id: int
    uuid: str
    name: str = "uztel"
    endpoint: str = '217.29.116.183'
    username: str = '781131202'
    channelCount: int = 1
    active: bool = True
    created_at: str


class CallInput(BaseModel):
    callUUID: str = '00000000-0000-0000-0000-000000000000'
    phone: constr(strip_whitespace=True, pattern=r'^(\d{9})$') = '907303455'
    client_name: str

    class Config:
        from_attributes = True


class CampaignInput(BaseModel):
    name: str = 'Debt notice'
    audio: str = 'https://storage.yandexcloud.net/myaudios/azizzzz.wav'
    retryCount: int = 3
    sip_uuid: str = 'uztel'
    channelCount: int = 1

    class Config:
        from_attributes = True


class GetCampaign(BaseModel):
    uuid: str
    name: str
    audio_duration: int
    retryCount: int = 3
    sip_name: str
    channelCount: int = 1
    status: str
    startDate: str
    endDate: str = ''

    class Config:
        from_attributes = True


class GetCall(BaseModel):
    id: int
    phone: str
    campaignName: str
    status: str = 'PENDING'
    recording: str
    duration: int
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
