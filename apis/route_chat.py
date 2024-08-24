import asyncio
import logging
import sys
import uuid
from datetime import datetime
from io import BytesIO

import pandas as pd
import requests
from environs import Env
from fastapi import APIRouter, BackgroundTasks, Request, Depends, UploadFile, File, Form
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from db.call_crud import bulk_create_call, get_call, cancel_calls, get_call_history, get_target_calls, get_calls
from db.campaign_crud import create_campaign, update_campaign, get_campaign, get_campaigns
from db.models import CallHistory, Campaign, CampaignStatus, CallStatus
from db.session import get_db
from db.sip_crud import get_sip, create_sip, get_active_sips
from schemas.input_query import CampaignInput, SipCreate, CampaignCountResponse
from script import add_sip, call_number, cancel_campaign, empty_channels, pause_campaign, \
    resume_campaign, get_duration

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])

env = Env()
env.read_env()
router = APIRouter()


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


async def call_concurrent(query, db, sip, campaign, audio_path, call_targets):
    tasks = []
    semaphore = asyncio.Semaphore(query.channelCount)

    async def call_one_by_one(targets):
        for callinfo in targets:
            db_call = get_call(db, callinfo.callUUID)
            db.refresh(campaign)
            if campaign.status.value == 'IN_PROGRESS':
                await call_number(db, sip, db_call, callinfo.phone, audio_path, query.retryCount, callinfo.callUUID)
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
                await call_number(db, sip, db_call, callinfo.phone, audio_path, query.retryCount, callinfo.callUUID)
            else:
                cancel_calls(db, campaign.uuid)

    if query.channelCount == 1:
        await call_one_by_one(call_targets)
    else:
        for callinfo in call_targets:
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


async def main_call(query, db, sip, campaign, audio_path, targets):
    await call_concurrent(query, db, sip, campaign, audio_path, targets)
    db.refresh(campaign)
    end_date_var = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if campaign.status.value == 'IN_PROGRESS':
        camp_status = 'FINISHED'
    elif campaign.status.value == 'PAUSED':
        return
    else:
        camp_status = 'CANCELLED'
    update_campaign(db, campaign, camp_status, endDate=end_date_var)


async def retry_main_call(db, campaign: Campaign):
    calls = get_call_history(campaign.uuid, db)
    retryCount = campaign.retryCount
    audio_path = campaign.audio
    sip = get_sip(db, campaign.sip_uuid)
    channelCount = campaign.channelCount
    tasks = []

    async def call_one_by_one(targets):
        for callinfo in targets:
            db_call = get_call(db, callinfo.callUUID)
            db.refresh(campaign)
            if db_call.status.value == 'PENDING':
                if campaign.status.value == 'IN_PROGRESS':
                    await call_number(db, sip, db_call, callinfo.phone, audio_path, retryCount, callinfo.callUUID)
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
                await call_number(db, sip, db_call, callinfo.phone, audio_path, retryCount, callinfo.callUUID)
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


async def send_response(db, query, query_uuid, audio_path: str, sip, df):
    duration = get_duration(audio_path)
    if duration:
        campaign = create_campaign(db=db, uuid=query_uuid, name=query.name, audio=audio_path,
                                   retryCount=query.retryCount,
                                   channelCount=query.channelCount, sip_uuid=sip.uuid, duration=duration)
    else:
        campaign = create_campaign(db=db, uuid=query_uuid, name=query.name, audio=audio_path,
                                   retryCount=query.retryCount,
                                   channelCount=query.channelCount, sip_uuid=sip.uuid)
    calls = []
    df['phone'] = df['phone'].astype(str)
    targets = get_target_calls(df)
    for k in targets:
        calls.append(CallHistory(uuid=k.callUUID, sip_id=sip.id, campaign_uuid=campaign.uuid, phone=k.phone,
                                 status='PENDING'))
    bulk_create_call(db, calls)
    # if is_work_time():
    query.channelCount = empty_channels(db, sip, campaign)
    print("Channel Count: " + str(query.channelCount))
    if query.channelCount > 0:
        campaign.status = 'IN_PROGRESS'
        campaign.startDate = datetime.now()
        campaign.channelCount = query.channelCount
        campaign = update_campaign(db, campaign)
        await main_call(query, db, sip, campaign, audio_path, targets)
    else:
        camp_status = 'BUSY'
        update_campaign(db, campaign, camp_status)
    # else:
    #     camp_status = 'PAUSED'
    #     update_campaign(db, campaign, camp_status)


@router.post("/campaign")
async def send_message(
        background_tasks: BackgroundTasks,
        name: str = Form("Debt notice"),  # Default value set to 'Debt notice'
        audio: str = Form("https://storage.yandexcloud.net/myaudios/ai_telephony/3.wav"),  # Default audio URL
        retryCount: int = Form(3),  # Default retry count
        sip_uuid: str = Form("uztel"),  # Default SIP UUID
        channelCount: int = Form(1),  # Default channel count
        file: UploadFile = File(...),  # File upload, no default as it is required
        db: Session = Depends(get_db)
):
    # You can now access the form data and file upload
    query = CampaignInput(
        name=name,
        audio=audio,
        retryCount=retryCount,
        sip_uuid=sip_uuid,
        channelCount=channelCount,
    )
    try:
        sip = get_sip(db, query.sip_uuid)
    except Exception as e:
        return JSONResponse(status_code=500,
                            content={"message": f"Campaign yaratishda xatolik: {str(e)}", "status": 500})

    content = await file.read()

    # Convert the content into a pandas DataFrame
    if file.filename.endswith('.csv'):
        df = pd.read_csv(BytesIO(content))
    elif file.filename.endswith('.xlsx'):
        df = pd.read_excel(BytesIO(content))
    else:
        return JSONResponse(content={"message": "Fayl formati noto'g'ri"}, status_code=400)

    if sip and sip.active:
        # Save audio file, if required
        freeswitch_loc = env.str('AUDIO_LOC')
        query_uuid = str(uuid.uuid4())
        audio_path = f"{freeswitch_loc}{query_uuid}.wav"
        audio_exists = save_to_file(query.audio, audio_path)
        if audio_exists:
            background_tasks.add_task(send_response, db, query, query_uuid, audio_path, sip, df)
            return JSONResponse(status_code=200,
                                content={"message": "Campaign muvaffaqiyatli yaratildi!", "status": 200})
        else:
            return JSONResponse(status_code=400,
                                content={"message": f"Audio formati noto'g'ri: {query.audio}!", "status": 400})
    else:
        return JSONResponse(status_code=400, content={"message": "Sip user topilmadi!", "status": 400})


@router.post("/sip")
async def send_message(query: SipCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        sip_uuid = str(uuid.uuid4())
        create_sip(db, name=query.name, username=query.username, password=query.password, endpoint=query.endpoint,
                   active=False, uuid=sip_uuid, channelCount=query.channelCount)
        background_tasks.add_task(add_sip, db, query, sip_uuid)
        return JSONResponse(status_code=200, content={"message": "Sip muvaffaqiyatli yaratildi!", "uuid": sip_uuid})
    except Exception as e:
        return JSONResponse(status_code=500,
                            content={"message": f"Sip yaratishda xatolik: {str(e)}", "status": 500})


@router.get("/get_sips")
async def get_all_sip(db: Session = Depends(get_db)):
    all_sips = get_active_sips(db)
    return all_sips


@router.get("/get_campaigns")
async def get_all_camp(is_active: bool = False, db: Session = Depends(get_db)):
    all_camps = get_campaigns(db, active=is_active)
    return all_camps


@router.get("/get_calls")
async def get_all_call(db: Session = Depends(get_db)):
    all_calls = get_calls(db)
    return all_calls


@router.get("/pause-campaign")
async def send_message(uuid: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        campaign = get_campaign(db, uuid)
        if campaign:
            background_tasks.add_task(pause_campaign, db, uuid)
            return JSONResponse(status_code=200,
                                content={"message": "Campaign muvaffaqiyatli to'xtatildi!", "status": 200})
        else:
            return JSONResponse(status_code=400,
                                content={"message": "Bunday campaign mavjud emas!", "status": 400})
    except Exception as e:
        return JSONResponse(status_code=500,
                            content={"message": f"Campaign pause qilishda xatolik: {str(e)}", "status": 500})


@router.get("/resume-campaign")
async def send_message(uuid: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        campaign = get_campaign(db, uuid)
        if campaign:
            background_tasks.add_task(resume_campaign, db, uuid, retry_main_call)
            return JSONResponse(status_code=200,
                                content={"message": "Campaign muvaffaqiyatli davom ettirildi!", "status": 200})
        else:
            return JSONResponse(status_code=400,
                                content={"message": "Bunday campaign mavjud emas!", "status": 400})
    except Exception as e:
        return JSONResponse(status_code=500,
                            content={"message": f"Campaign resume qilishda xatolik: {str(e)}", "status": 500})


@router.get("/cancel-campaign")
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


# @router.get("/active_campaigns", response_model=List[ActiveCampaignResponse])
# async def get_active_campaigns(db: Session = Depends(get_db)):
#     campaigns = db.query(Campaign).filter(Campaign.status == CampaignStatus.IN_PROGRESS).all()
#
#     active_campaigns = []
#
#     for campaign in campaigns:
#         total_calls = db.query(CallHistory).filter(CallHistory.campaign_uuid == campaign.uuid).count()
#         completed_duration_sum = db.query(func.sum(CallHistory.duration)).filter(
#             CallHistory.campaign_uuid == campaign.uuid,
#             CallHistory.duration.isnot(None)
#         ).scalar() or 0
#         active_call_count = db.query(CallHistory).filter(
#             CallHistory.campaign_uuid == campaign.uuid,
#             CallHistory.status.in_([CallStatus.RINGING, CallStatus.PENDING])
#         ).count()
#         remaining_time = active_call_count * campaign.audio_duration
#         time_since_started = (datetime.now() - campaign.startDate).total_seconds()
#
#         active_campaigns.append({
#             "uuid": campaign.uuid,
#             "total_calls": total_calls,
#             "completed_time": int(completed_duration_sum / 60),
#             "remaining_time": int(remaining_time / 60),
#             "time_since_started": int(time_since_started / 60)
#         })
#
#     return active_campaigns


@router.get("/stop_all")
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
                                                                       CampaignStatus.PENDING,
                                                                       CampaignStatus.BUSY])).all()
            for k in campaigns:
                cancel_campaign(db, k.uuid)
            return JSONResponse(status_code=200,
                                content={"message": "Campaignlar muvaffaqiyatli bekor qilindi", "status": 200})
    except Exception as e:
        return JSONResponse(status_code=500,
                            content={"message": f"Campaign bekor qilishda xatolik: {str(e)}", "status": 500})
