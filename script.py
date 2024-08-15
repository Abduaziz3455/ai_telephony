import asyncio
import logging
import subprocess
import sys
import time
from datetime import datetime

from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from db.call_crud import get_call, update_call
from db.campaign_crud import update_campaign, get_campaign, get_status, update_status
from db.gateway_crud import create_gateway, get_gateway, invalid_gateways
from db.models import Campaign, Gateway, CallHistory
from pika_client import PikaClient
from schemas.input_query import CallUpdate, ChannelCreate, CampaignUpdate, ChannelStatus
from environs import Env

from ssh_command import ssh_connect_B

env = Env()
env.read_env()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])


def log_incoming_message(cls, message: dict):
    """Method to do something meaningful with the incoming message"""
    logging.info('Here we got incoming message %s', message)


pika_client = PikaClient(log_incoming_message, env.str("CALL_QUEUE"))
pika_channel = PikaClient(log_incoming_message, env.str("SIP_QUEUE"))


async def send_channel_status(channel: ChannelStatus):
    await pika_channel.send_message(channel.dict())


async def send_call_update(call: CallUpdate):
    await pika_client.send_message(call.dict())


async def send_campaign_update(campaign: CampaignUpdate):
    await pika_client.send_message(campaign.dict())


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


async def update_and_send(db, call, message, status, recording=None, duration=None):
    call.status = status
    update_call(db, call, recording, duration)
    message.status = status
    if recording:
        message.audio = f"{env.str('BASE_URL')}{recording}"
    if duration:
        message.duration = duration
    await send_call_update(message)


async def call_number(db: Session, gateway: ChannelCreate, call: CallHistory, number: str, audioPath: str,
                      retryTime: int, UUID: str):
    # Construct the command
    command = f'fs_cli -x "luarun call_number.lua {gateway.uuid} {gateway.username} {number} {audioPath} {retryTime} {UUID}"'
    try:
        if call.status.value == 'PENDING':
            # Execute the command and capture the output
            if is_work_time():
                status = get_status(db)
                db.refresh(status)
                print("Reload status: ", status.reloadStatus)
                print("Call active: ", status.call_active)
                if status.reloadStatus:
                    update_status(db, status)
                    ssh_connect_B(command)
                else:
                    process = await asyncio.create_subprocess_shell(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                call.status = "RINGING"
                call.startDate = datetime.now()
                update_call(db, call)

                message = CallUpdate(callUUID=UUID, campaignUUID=call.campaign_uuid,
                                     startDate=call.startDate.strftime('%Y-%m-%d %H:%M:%S'), status=call.status,
                                     channelUUID=gateway.uuid)
                await send_call_update(message)

                time_count = 0

                while True:
                    call = get_call(db, UUID)
                    db.refresh(call)
                    call_status = call.status.value
                    print(call_status)

                    if call_status == 'RINGING':
                        if (time_count >= 30 and retryTime in [0, 1]) or (time_count >= 70 and retryTime >= 2):
                            await update_and_send(db, call, message, 'DROPPED')
                            update_status(db, status)
                            break
                        time_count += 1
                        await asyncio.sleep(3)
                    elif call_status in ['COMPLETED', 'DROPPED', 'TERMINATED']:
                        recording = f"recordings/{UUID}.wav"
                        if call.duration:
                            await update_and_send(db, call, message, call_status, recording, call.duration)
                        else:
                            await update_and_send(db, call, message, call_status, recording)
                        break
                    else:
                        await update_and_send(db, call, message, 'MISSED')
                        break
            else:
                camp = get_campaign(db, call.campaign_uuid)
                update_campaign(db, camp, 'PAUSED')
                campaign = CampaignUpdate(uuid=call.campaign_uuid, status='PAUSED')
                await send_campaign_update(campaign)
    except subprocess.TimeoutExpired:
        print("Command execution timed out.")
        return "timeout"  # Handle timeout
    except Exception as e:
        print(f"An error occurred: {e}")
        return "error"  # Handle any other errors


async def add_gateway(db: Session, query: ChannelCreate):
    # Construct the command to run the Lua script with FreeSWITCH
    create_gateway(db, name=query.name, username=query.username, password=query.password,
                   endpoint=query.endpoint, active=False, uuid=query.uuid, channelCount=query.channelCount)
    try:
        # count = 0
        while True:
            a_active = await check_calls(db)
            b_active = await check_calls(db, B_point=True)
            print("a_point: ", a_active)
            print("b_point: ", b_active)

            status = get_status(db)
            sip = get_gateway(db, query.uuid)
            if not a_active:
                # count += 1
                # # Execute the command
                # if count == 1:
                command = f'fs_cli -x "luarun add_gateway.lua {query.uuid} {query.endpoint} {query.username} {query.password}"'
                process = await asyncio.create_subprocess_shell(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                await process.communicate()
                # Adding a delay to ensure the command execution completes
                await asyncio.sleep(5)
                db.refresh(sip)
                message = ChannelStatus(uuid=sip.uuid, active=sip.active)
                print(f"SIP UUID: ***{message.uuid}***")
                print(f"SIP ACTIVE: ***{message.active}***")
                await send_channel_status(message)
                print("Statusni reload qilish False ga o'tdi")
                status.reloadStatus = False
                update_status(db, status)
                break
            else:
                print("Statusni reload qilish TRUE ga o'tdi")
                status.reloadStatus = True
                update_status(db, status)
                await asyncio.sleep(5)

        while True:
            b_active = await check_calls(db, B_point=True)
            if not b_active:
                if sip.active:
                    command1 = f'fs_cli -x "reloadxml"'
                    command2 = f'fs_cli -x "reload mod_sofia"'
                    ssh_connect_B(command1, command2)
                break
            else:
                await asyncio.sleep(5)

    except Exception as e:
        # Log the exception if any
        print(f"An error occurred: {e}")
        return None


async def check_gateway(db: Session):
    command = 'fs_cli -x "luarun check_gateway.lua"'
    try:
        process = await asyncio.create_subprocess_shell(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        await process.communicate()
        false_sips = invalid_gateways(db)
        return false_sips
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


async def check_calls(db: Session, B_point: bool = False):
    try:
        if not B_point:
            command = 'fs_cli -x "luarun check_calls.lua"'
            process = await asyncio.create_subprocess_shell(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            await process.communicate()
            status = get_status(db)
            await asyncio.sleep(3)
            db.refresh(status)
            if status.call_active:
                return True
            return False
        else:
            command = 'fs_cli -x "luarun check_calls_B.lua"'
            ssh_connect_B(command)
            status = get_status(db)
            await asyncio.sleep(3)
            db.refresh(status)
            if status.call_active_b:
                return True
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


def empty_channels(db: Session, gateway: Gateway, campaign: Campaign):
    # busy channels count
    query = select(func.sum(Campaign.channelCount)).where(
        and_(
            Campaign.status == 'IN_PROGRESS',
            Campaign.gateway_uuid == gateway.uuid
        )
    )
    busy_channel = db.execute(query).scalar()
    busy_channel = busy_channel if busy_channel else 0
    empty_channel = gateway.channelCount - busy_channel
    print("Empty channels: ", empty_channel)
    print("Busy channels: ", busy_channel)
    print("Gateway channels: ", gateway.channelCount)
    print('Campaign channel count', campaign.channelCount)
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


def is_work_time(start_str='8:00', end_str='20:00'):
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
                gateway = get_gateway(db, new_camp.gateway_uuid)
                channels = empty_channels(db, gateway, new_camp)
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


async def pause_campaign(db, campaign_uuid, send_campaign_update):
    campaign = get_campaign(db, campaign_uuid)
    campaign = update_campaign(db, campaign, 'PAUSED')
    message = CampaignUpdate(uuid=campaign.uuid, status=campaign.status)
    await send_campaign_update(message)


async def resume_campaign(db, campaign_uuid, send_campaign_update, retry_main_call):
    campaign = get_campaign(db, campaign_uuid)
    gateway = get_gateway(db, campaign.gateway_uuid)
    channels = empty_channels(db, gateway, campaign)
    if channels >= 1:
        campaign.status = 'IN_PROGRESS'
        campaign.channelCount = channels
        campaign = update_campaign(db, campaign)
        message = CampaignUpdate(uuid=campaign.uuid, status=campaign.status)
        await send_campaign_update(message)
        await retry_main_call(db, campaign)
    else:
        camp_status = 'BUSY'
        update_campaign(db, campaign, camp_status)
        message = CampaignUpdate(uuid=campaign.uuid, status=camp_status)
        await send_campaign_update(message)
