local sip = argv[1]
local caller_id_number = argv[2]
local number = argv[3]
local audioFile = argv[4]
local retryTime = tonumber(argv[5])
local UUID = argv[6]
local recording_path = "recordings/" .. UUID .. ".wav"

-- Connect to the PostgreSQL database
local dbh = freeswitch.Dbh("postgres://postgres:abdu3421@127.0.0.1:5432/robot_call")
assert(dbh:connected(), "Failed to connect to the database")

local function update_stat_func(dbh, UUID, status, duration)
    local update_status
    freeswitch.consoleLog("INFO", "STATUS: " .. status .. "\n")
    if duration then
        freeswitch.consoleLog("INFO", "TRUE: " .. duration .. " seconds\n")
        update_status = string.format([[UPDATE callhistory SET status = '%s', duration = %s WHERE uuid = '%s']], status, duration, UUID)
    else
        update_status = string.format([[UPDATE callhistory SET status = '%s' WHERE uuid = '%s']], status, UUID)
    end

    local success, err = dbh:query(update_status)
    if not success then
        freeswitch.consoleLog("ERROR", "Database update failed: " .. tostring(err) .. "\n")
    end
end

local function hangup_stat_func(session)
    local hangup_cause = session:getVariable("hangup_cause")
    freeswitch.consoleLog(hangup_cause and "INFO" or "WARNING", hangup_cause and "Call hangup cause: " .. hangup_cause .. "\n" or "No hangup cause available\n")
    return hangup_cause
end

local function round(value)
    return math.floor(value)
end

local function os_capture(cmd)
    local f = assert(io.popen(cmd, 'r'))
    local s = assert(f:read('*a'))
    f:close()
    return s
end


local attempt = 0
local final_status
local duration
local hangup_cause


repeat
    attempt = attempt + 1
    local session_str = string.format("{ignore_early_media=true,originate_timeout=40,origination_caller_id_number=%s}sofia/gateway/%s/%s", caller_id_number, sip, number)
    local new_session = freeswitch.Session(session_str)
    update_stat_func(dbh, UUID, 'RINGING', nil)

    -- Check if the session is ready
    if new_session:ready() then
        -- Measure time before answering the call
        local start_time = os.time()
        -- Answer the call
        new_session:answer()
        -- Start recording the call
        new_session:execute("set", "RECORD_STEREO=true")
        new_session:execute("record_session", recording_path)
        new_session:streamFile(audioFile)
        -- Play the audio file
        freeswitch.consoleLog("WARNING", "Audio Path: " .. audioFile .. "\n")
        -- Insert audio information to database
        new_session:recordFile("recordings/" .. UUID .. "_response.wav", 10, 500, 5)
        local insert_audio_query = string.format("INSERT INTO voicehistory (voice, scriptId, payDate, reason, callId, resVoice, finished) VALUES ('%s', '', '', '', ", UUID, audioFile)
        local success, err = dbh:query(insert_audio_query)
        if not success then
            freeswitch.consoleLog("ERROR", "Failed to insert audio information: " .. tostring(err) .. "\n")
        end
        -- Call Python script to analyze the audio file.
        local analysis_result = os_capture("C:/Users/Abdua/anaconda3/envs/chatbot/python.exe C:/Users/Abdua/Downloads/analyze_audio.py " .. UUID)
        freeswitch.consoleLog("INFO", "Audio Analysis Result: " .. analysis_result .. "\n")
        -- Pause for one second
        freeswitch.msleep(3000)
        
        -- Select `resaudio` from the `audio` table
        local select_audio_query = string.format([[
            SELECT resaudio FROM audio WHERE uuid='%s'
        ]], UUID)
        
        local resaudio
        local query_success = dbh:query(select_audio_query, function(row)
            resaudio = row.resaudio
        end)
        
        if query_success then
            new_session:streamFile(resaudio)
            freeswitch.consoleLog("INFO", "Resaudio: " .. (resaudio or "nil") .. "\n")
        else
            freeswitch.consoleLog("ERROR", "Failed to select resaudio: " .. tostring(err) .. "\n")
        end
        
        -- Stop recording
        new_session:execute("stop_record_session", recording_path)
        -- Measure time before hanging up the call
        local end_time = os.time()
        -- Hang up the call
        new_session:hangup()
        -- Calculate the call duration and round it
        duration = round(end_time - start_time)
    end

    -- Get the hangup status
    local hangup_status = hangup_stat_func(new_session)
    -- Get the current state of the session
    local g_state = new_session:getState()
    freeswitch.consoleLog("WARNING", "g-STATE status: " .. g_state .. "\n")
    if hangup_status then
        freeswitch.consoleLog("WARNING", "hangup_status: " .. hangup_status .. "\n")
    else
        freeswitch.consoleLog("WARNING", "hangup_status: No hangup\n")
    end
    if hangup_cause then
        freeswitch.consoleLog("WARNING", "HANGUP_CAUSE: " .. hangup_cause .. "\n")
    else
        freeswitch.consoleLog("WARNING", "HANGUP_CAUSE: No HANGUP\n")
    end
    -- Determine the final status based on the session state and hangup cause
    if g_state == 'ERROR' then
        final_status = 'MISSED'
    else
        if g_state == 'CS_HANGUP' then
            final_status = 'COMPLETED'
        elseif g_state == 'CS_DESTROY' then
            if hangup_status == 'NORMAL_CLEARING' then
                final_status = 'TERMINATED'
            else
                final_status = 'DROPPED'
            end
        else
            final_status = 'DROPPED'
        end
        break
    end

until attempt >= retryTime
freeswitch.consoleLog("WARNING", "attempt: " .. attempt .. "\n")
update_stat_func(dbh, UUID, final_status, duration)

-- Close the database connection
dbh:release()
