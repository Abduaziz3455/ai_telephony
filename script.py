import asyncio
import logging
import subprocess
import sys
from datetime import datetime

from environs import Env
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from db.call_crud import get_call, update_call
from db.campaign_crud import update_campaign, get_campaign
from db.models import Campaign, Sip, CallHistory
from db.sip_crud import get_sip, invalid_sips
from schemas.input_query import SipCreate, CampaignUpdate, ChannelStatus, GetSip

env = Env()
env.read_env()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])


def get_duration(audioPath: str):
    try:
        import wave
        import contextlib
        with contextlib.closing(wave.open(audioPath, 'r')) as f:
            frames = f.getnframes()
            rate = f.getframerate()
            duration = frames / float(rate)
        return int(duration)
    except Exception as e:
        logging.error(f"Error with getting duration: {e}")
        return None


async def update_and_send(db, call, status, recording=None, duration=None):
    call.status = status
    update_call(db, call, recording, duration)
    # message.status = status
    # if recording:
    #     message.audio = f"{env.str('BASE_URL')}{recording}"
    # if duration:
    #     message.duration = duration


async def call_number(db: Session, sip: GetSip, call: CallHistory, number: str, audioPath: str,
                      retryTime: int, UUID: str):
    # Construct the command
    command = f'fs_cli -x "luarun call_number.lua {sip.uuid} {sip.username} {number} {audioPath} {retryTime} {UUID}"'
    try:
        if call.status.value == 'PENDING':
            # Execute the command and capture the output
            if is_work_time():
                process = await asyncio.create_subprocess_shell(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                call.status = "RINGING"
                call.startDate = datetime.now()
                update_call(db, call)

                time_count = 0

                while True:
                    call = get_call(db, UUID)
                    db.refresh(call)
                    call_status = call.status.value
                    print(call_status)

                    if call_status == 'RINGING':
                        if (time_count >= 30 and retryTime in [0, 1]) or (time_count >= 70 and retryTime >= 2):
                            await update_and_send(db, call, 'DROPPED')
                            break
                        time_count += 1
                        await asyncio.sleep(3)
                    elif call_status in ['COMPLETED', 'DROPPED', 'TERMINATED']:
                        recording = f"recordings/{UUID}.wav"
                        if call.duration:
                            await update_and_send(db, call, call_status, recording, call.duration)
                        else:
                            await update_and_send(db, call, call_status, recording)
                        break
                    else:
                        await update_and_send(db, call, 'MISSED')
                        break
            else:
                camp = get_campaign(db, call.campaign_uuid)
                update_campaign(db, camp, 'PAUSED')
    except subprocess.TimeoutExpired:
        print("Command execution timed out.")
        return "timeout"  # Handle timeout
    except Exception as e:
        print(f"An error occurred: {e}")
        return "error"  # Handle any other errors


async def add_sip(db: Session, query: SipCreate, sip_uuid):
    # Construct the command to run the Lua script with FreeSWITCH
    try:
        while True:
            sip = get_sip(db, sip_uuid)
            command = f'fs_cli -x "luarun add_sip.lua {sip_uuid} {query.endpoint} {query.username} {query.password}"'
            process = await asyncio.create_subprocess_shell(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            await process.communicate()
            # Adding a delay to ensure the command execution completes
            await asyncio.sleep(5)
            db.refresh(sip)
            message = ChannelStatus(uuid=sip.uuid, active=sip.active)
            print(f"SIP UUID: ***{message.uuid}***")
            print(f"SIP ACTIVE: ***{message.active}***")
            break

    except Exception as e:
        # Log the exception if any
        print(f"An error occurred: {e}")
        return None


async def check_sip(db: Session):
    command = 'fs_cli -x "luarun check_sip.lua"'
    try:
        process = await asyncio.create_subprocess_shell(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        await process.communicate()
        false_sips = invalid_sips(db)
        return false_sips
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


async def check_calls():
    try:
        command = 'fs_cli -x "luarun check_calls.lua"'
        process = await asyncio.create_subprocess_shell(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        await process.communicate()
        return False

    except Exception as e:
        print(f"An error occurred: {e}")
        return True


def cancel_campaign(db: Session, uuid: str):
    camp = get_campaign(db, uuid)
    if camp:
        update_campaign(db, camp, 'CANCELLED', endDate=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        return True
    else:
        return False


def empty_channels(db: Session, sip: Sip, campaign: Campaign):
    # busy channels count
    query = select(func.sum(Campaign.channelCount)).where(
        and_(
            Campaign.status == 'IN_PROGRESS',
            Campaign.sip_uuid == sip.uuid
        )
    )
    busy_channel = db.execute(query).scalar()
    busy_channel = busy_channel if busy_channel else 0
    empty_channel = sip.channelCount - busy_channel
    # print("Empty channels: ", empty_channel)
    # print("Busy channels: ", busy_channel)
    # print("Sip channels: ", sip.channelCount)
    # print('Campaign channel count', campaign.channelCount)
    if campaign.channelCount <= empty_channel:
        return campaign.channelCount
    else:
        if empty_channel >= 1:
            return empty_channel
        else:
            return 0


def busy_campaign(db: Session):
    query = select(Campaign).where(Campaign.status == 'BUSY')
    campaign = db.execute(query).scalars().first()
    return campaign


def retry_campaign(db: Session):
    query = select(Campaign).where(Campaign.status == 'IN_PROGRESS')
    campaign = db.execute(query).scalars().first()
    return campaign


def is_work_time(start_str='07:00', end_str='03:00'):
    current_time = datetime.now().time()
    # Parse the start and end time strings
    start_time = datetime.strptime(start_str, "%H:%M").time()
    end_time = datetime.strptime(end_str, "%H:%M").time()

    return start_time <= current_time <= end_time


async def continue_campaign(db, send_campaign_update, retry_main_call, start=False):
    while True:
        if start:
            new_camp = retry_campaign(db)
        else:
            new_camp = busy_campaign(db)
        if new_camp:
            if is_work_time():
                print("New Campaign: ", new_camp)
                sip = get_sip(db, new_camp.sip_uuid)
                channels = empty_channels(db, sip, new_camp)
                if channels >= 1:
                    await asyncio.sleep(7)
                    new_camp.status = 'IN_PROGRESS'
                    new_camp.startDate = datetime.now()
                    new_camp.channelCount = channels
                    print("New Channel Count: " + str(new_camp.channelCount))
                    campaign = update_campaign(db, new_camp)
                    message = CampaignUpdate(uuid=campaign.uuid, status=campaign.status,
                                             startDate=campaign.startDate.strftime('%Y-%m-%d %H:%M:%S'))
                    await send_campaign_update(message)
                    await retry_main_call(db, campaign)
                else:
                    await asyncio.sleep(5)
            else:
                new_camp.status = 'PAUSED'
                campaign = update_campaign(db, new_camp)
                message = CampaignUpdate(uuid=campaign.uuid, status=campaign.status)
                await send_campaign_update(message)
        else:
            logging.info("No new campaign")
            break


async def pause_campaign(db, campaign_uuid):
    campaign = get_campaign(db, campaign_uuid)
    update_campaign(db, campaign, 'PAUSED')


async def resume_campaign(db, campaign_uuid, retry_main_call):
    campaign = get_campaign(db, campaign_uuid)
    sip = get_sip(db, campaign.sip_uuid)
    channels = empty_channels(db, sip, campaign)
    if channels >= 1:
        campaign.status = 'IN_PROGRESS'
        campaign.channelCount = channels
        campaign = update_campaign(db, campaign)
        await retry_main_call(db, campaign)
    else:
        camp_status = 'BUSY'
        update_campaign(db, campaign, camp_status)
