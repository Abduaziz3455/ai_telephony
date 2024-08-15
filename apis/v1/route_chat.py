import asyncio
import logging
import sys
from datetime import datetime
from typing import List

import requests
from environs import Env
from fastapi import APIRouter, BackgroundTasks, Request, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from db.call_crud import bulk_create_call, get_call, cancel_calls, get_call_history
from db.campaign_crud import create_campaign, update_campaign, get_campaign
from db.gateway_crud import delete_gateway, get_gateway
from db.models import CallHistory, Campaign, CampaignStatus, CallStatus
from db.session import get_db
from pika_client import PikaClient
from schemas.input_query import CampaignInput, CampaignUpdate, ChannelCreate, CampaignCountResponse, \
    ActiveCampaignResponse
from script import add_gateway, call_number, cancel_campaign, empty_channels, continue_campaign, pause_campaign, \
    resume_campaign, get_duration, is_work_time, send_campaign_update

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])


def log_incoming_message(cls, message: dict):
    """Method to do something meaningful with the incoming message"""
    logging.info('Here we got incoming message %s', message)


env = Env()
env.read_env()
router = APIRouter()
pika_client = PikaClient(log_incoming_message, env.str("CAMPAIGN_QUEUE"))


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    custom_errors = []

    for error in errors:
        field = error.get('loc')[-1]
        message = error.get('msg')
        custom_errors.append({"field": field, "message": message})
    logging.error(custom_errors)
    return JSONResponse(status_code=400, content={"detail": custom_errors})


def save_to_file(audio_url, file_path: str):
    try:
        content = requests.get(audio_url).content
        with open(file_path, 'wb') as audio_file:
            audio_file.write(content)
        logging.info(f"Audio file saved successfully at {file_path}")
        return True
    except Exception as e:
        logging.error(f"Failed to save audio file: {e}")
        return False


async def call_concurrent(query, db, gateway, campaign, audio_path):
    tasks = []
    semaphore = asyncio.Semaphore(query.channelCount)

    async def call_one_by_one(targets):
        for callinfo in targets:
            db_call = get_call(db, callinfo.callUUID)
            db.refresh(campaign)
            if campaign.status.value == 'IN_PROGRESS':
                await call_number(db, gateway, db_call, callinfo.phone, audio_path, query.retryCount, callinfo.callUUID)
            elif campaign.status.value == 'PAUSED':
                break
            else:
                cancel_calls(db, campaign.uuid)
                break

    async def call_with_semaphore(callinfo):
        async with semaphore:
            db_call = get_call(db, callinfo.callUUID)
            db.refresh(campaign)
            if campaign.status.value == 'IN_PROGRESS':
                await call_number(db, gateway, db_call, callinfo.phone, audio_path, query.retryCount, callinfo.callUUID)
            else:
                cancel_calls(db, campaign.uuid)

    if query.channelCount == 1:
        await call_one_by_one(query.targets)
    else:
        for callinfo in query.targets:
            if campaign.status.value == 'IN_PROGRESS':
                task = asyncio.create_task(call_with_semaphore(callinfo))
                tasks.append(task)
            elif campaign.status.value == 'PAUSED':
                break
            else:
                cancel_calls(db, campaign.uuid)
                break

        if tasks:
            await asyncio.gather(*tasks)


async def main_call(query, db, gateway, campaign, audio_path):
    await call_concurrent(query, db, gateway, campaign, audio_path)
    db.refresh(campaign)
    end_date_var = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if campaign.status.value == 'IN_PROGRESS':
        camp_status = 'FINISHED'
    elif campaign.status.value == 'PAUSED':
        return
    else:
        camp_status = 'CANCELLED'
    update_campaign(db, campaign, camp_status, endDate=end_date_var)
    message = CampaignUpdate(uuid=campaign.uuid, status=camp_status,
                             startDate=campaign.startDate.strftime('%Y-%m-%d %H:%M:%S'), endDate=end_date_var)
    await send_campaign_update(message)


async def retry_main_call(db, campaign: Campaign):
    calls = get_call_history(campaign.uuid, db)
    retryCount = campaign.retryCount
    audio_path = campaign.audio
    gateway = get_gateway(db, campaign.gateway_uuid)
    channelCount = campaign.channelCount
    tasks = []

    async def call_one_by_one(targets):
        for callinfo in targets:
            db_call = get_call(db, callinfo.callUUID)
            db.refresh(campaign)
            if db_call.status.value == 'PENDING':
                if campaign.status.value == 'IN_PROGRESS':
                    await call_number(db, gateway, db_call, callinfo.phone, audio_path, retryCount, callinfo.callUUID)
                elif campaign.status.value == 'PAUSED':
                    break
                else:
                    cancel_calls(db, campaign.uuid)
                    break

    async def call_with_semaphore(callinfo):
        db_call = get_call(db, callinfo.callUUID)
        db.refresh(campaign)
        if db_call.status.value == 'PENDING':
            if campaign.status.value == 'IN_PROGRESS':
                await call_number(db, gateway, db_call, callinfo.phone, audio_path, retryCount, callinfo.callUUID)
            else:
                cancel_calls(db, campaign.uuid)

    if channelCount == 1:
        await call_one_by_one(calls)
    else:
        for callinfo in calls:
            if campaign.status.value == 'IN_PROGRESS':
                task = asyncio.create_task(call_with_semaphore(callinfo))
                tasks.append(task)
            elif campaign.status.value == 'PAUSED':
                break
            else:
                cancel_calls(db, campaign.uuid)
                break

        if tasks:
            logging.info("Gathering tasks")
            await asyncio.gather(*tasks)
            logging.info("Tasks gathered")

    db.refresh(campaign)
    end_date_var = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if campaign.status.value == 'IN_PROGRESS':
        camp_status = 'FINISHED'
    elif campaign.status.value == 'PAUSED':
        return
    else:
        camp_status = 'CANCELLED'
    update_campaign(db, campaign, camp_status, endDate=end_date_var)
    message = CampaignUpdate(uuid=campaign.uuid, status=camp_status,
                             startDate=campaign.startDate.strftime('%Y-%m-%d %H:%M:%S'), endDate=end_date_var)
    await send_campaign_update(message)


async def send_response(db, query, audio_path: str, sips: list):
    gateway = sips[0]
    duration = get_duration(audio_path)
    if duration:
        campaign = create_campaign(db=db, uuid=query.uuid, name=query.name, audio=audio_path, retryCount=query.retryCount,
                                   channelCount=query.channelCount, gateway_uuid=gateway.uuid, duration=duration)
    else:
        campaign = create_campaign(db=db, uuid=query.uuid, name=query.name, audio=audio_path,
                                   retryCount=query.retryCount,
                                   channelCount=query.channelCount, gateway_uuid=gateway.uuid)
    calls = []
    for k in query.targets:
        calls.append(CallHistory(uuid=k.callUUID, gateway_id=gateway.id, campaign_uuid=campaign.uuid, phone=k.phone,
                                 status='PENDING'))
    bulk_create_call(db, calls)
    if is_work_time():
        query.channelCount = empty_channels(db, gateway, campaign)
        print("Channel Count: " + str(query.channelCount))
        if query.channelCount > 0:
            campaign.status = 'IN_PROGRESS'
            campaign.startDate = datetime.now()
            campaign.channelCount = query.channelCount
            campaign = update_campaign(db, campaign)
            await main_call(query, db, gateway, campaign, audio_path)
            await continue_campaign(db, send_campaign_update, retry_main_call)
        else:
            camp_status = 'BUSY'
            update_campaign(db, campaign, camp_status)
            message = CampaignUpdate(uuid=campaign.uuid, status=camp_status)
            await send_campaign_update(message)
    else:
        camp_status = 'PAUSED'
        update_campaign(db, campaign, camp_status)
        message = CampaignUpdate(uuid=campaign.uuid, status=camp_status)
        await send_campaign_update(message)


@router.post("/campaign")
async def send_message(query: CampaignInput, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    registered_sips = []

    for sip in query.channels:
        try:
            gate = get_gateway(db, sip)
            if gate:
                if gate.active:
                    registered_sips.append(gate)
        except Exception as e:
            return JSONResponse(status_code=500,
                                content={"message": f"Campaign yaratishda xatolik: {str(e)}", "status": 500})

    if registered_sips:
        # Save audio file, if required
        freeswitch_loc = env.str('AUDIO_LOC')
        audio_path = f"{freeswitch_loc}{query.uuid}.wav"
        audio_exists = save_to_file(query.audio, audio_path)
        if audio_exists:
            background_tasks.add_task(send_response, db, query, audio_path, registered_sips)
            return JSONResponse(status_code=200,
                                content={"message": "Campaign muvaffaqiyatli yaratildi!", "status": 200})
        else:
            return JSONResponse(status_code=400,
                                content={"message": f"Audio formati noto'g'ri: {query.audio}!", "status": 400})
    else:
        return JSONResponse(status_code=400, content={"message": "Sip user topilmadi!", "status": 400})


@router.post("/channel")
async def send_message(query: ChannelCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        background_tasks.add_task(add_gateway, db, query)
        return JSONResponse(status_code=200, content={"message": "Sip muvaffaqiyatli yaratildi!", "status": 200})
    except Exception as e:
        return JSONResponse(status_code=500,
                            content={"message": f"Sip yaratishda xatolik: {str(e)}", "status": 500})


@router.post("/pause-campaign")
async def send_message(uuid: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        campaign = get_campaign(db, uuid)
        if campaign:
            background_tasks.add_task(pause_campaign, db, uuid, send_campaign_update)
            return JSONResponse(status_code=200,
                                content={"message": "Campaign muvaffaqiyatli to'xtatildi!", "status": 200})
        else:
            return JSONResponse(status_code=400,
                                content={"message": "Bunday campaign mavjud emas!", "status": 400})
    except Exception as e:
        return JSONResponse(status_code=500,
                            content={"message": f"Campaign pause qilishda xatolik: {str(e)}", "status": 500})


@router.post("/resume-campaign")
async def send_message(uuid: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        campaign = get_campaign(db, uuid)
        if campaign:
            background_tasks.add_task(resume_campaign, db, uuid, send_campaign_update, retry_main_call)
            return JSONResponse(status_code=200,
                                content={"message": "Campaign muvaffaqiyatli davom ettirildi!", "status": 200})
        else:
            return JSONResponse(status_code=400,
                                content={"message": "Bunday campaign mavjud emas!", "status": 400})
    except Exception as e:
        return JSONResponse(status_code=500,
                            content={"message": f"Campaign resume qilishda xatolik: {str(e)}", "status": 500})


@router.post("/cancel-campaign")
async def send_message(uuid: str, db: Session = Depends(get_db)):
    try:
        cancelled = cancel_campaign(db, uuid)
        if cancelled:
            return JSONResponse(status_code=200,
                                content={"message": "Campaign muvaffaqiyatli bekor qilindi", "status": 200})
        else:
            return JSONResponse(status_code=400, content={"message": "Bunday campaign mavjud emas!", "status": 400})
    except Exception as e:
        return JSONResponse(status_code=500,
                            content={"message": f"Campaign bekor qilishda xatolik: {str(e)}", "status": 500})


@router.get("/active_counts", response_model=CampaignCountResponse)
async def get_active_counts(db: Session = Depends(get_db)):
    campaigns = db.query(Campaign).filter(Campaign.status == CampaignStatus.IN_PROGRESS)
    call_count = db.query(CallHistory).filter(CallHistory.status == CallStatus.RINGING,
                                              CallHistory.campaign_uuid.in_([x.uuid for x in campaigns])).count()

    return {
        "campaign_count": campaigns.count(),
        "call_count": call_count
    }


@router.get("/active_campaigns", response_model=List[ActiveCampaignResponse])
async def get_active_campaigns(db: Session = Depends(get_db)):
    campaigns = db.query(Campaign).filter(Campaign.status == CampaignStatus.IN_PROGRESS).all()

    active_campaigns = []

    for campaign in campaigns:
        total_calls = db.query(CallHistory).filter(CallHistory.campaign_uuid == campaign.uuid).count()
        completed_duration_sum = db.query(func.sum(CallHistory.duration)).filter(
            CallHistory.campaign_uuid == campaign.uuid,
            CallHistory.duration.isnot(None)
        ).scalar() or 0
        active_call_count = db.query(CallHistory).filter(
            CallHistory.campaign_uuid == campaign.uuid,
            CallHistory.status.in_([CallStatus.RINGING, CallStatus.PENDING])
        ).count()
        remaining_time = active_call_count * campaign.audio_duration
        time_since_started = (datetime.now() - campaign.startDate).total_seconds()

        active_campaigns.append({
            "uuid": campaign.uuid,
            "total_calls": total_calls,
            "completed_time": int(completed_duration_sum / 60),
            "remaining_time": int(remaining_time / 60),
            "time_since_started": int(time_since_started / 60)
        })

    return active_campaigns


@router.post("/stop_all")
async def send_message(uuid: str = None, db: Session = Depends(get_db)):
    try:
        if uuid:
            cancelled = cancel_campaign(db, uuid)
            if cancelled:
                return JSONResponse(status_code=200,
                                    content={"message": "Campaign muvaffaqiyatli bekor qilindi", "status": 200})
            else:
                return JSONResponse(status_code=400, content={"message": "Bunday campaign mavjud emas!", "status": 400})
        else:
            campaigns = db.query(Campaign).filter(Campaign.status.in_([CampaignStatus.IN_PROGRESS,
                                                                       CampaignStatus.PENDING, CampaignStatus.BUSY])).all()
            for k in campaigns:
                cancel_campaign(db, k.uuid)
            return JSONResponse(status_code=200,
                                content={"message": "Campaignlar muvaffaqiyatli bekor qilindi", "status": 200})
    except Exception as e:
        return JSONResponse(status_code=500,
                            content={"message": f"Campaign bekor qilishda xatolik: {str(e)}", "status": 500})
