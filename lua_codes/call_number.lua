local sip = argv[1]
local caller_id_number = argv[2]
local number = argv[3]
local lang = argv[4]
local retryTime = tonumber(argv[5])
local UUID = argv[6]
local recording_path = "recordings/" .. UUID .. ".wav"

local db_user = os.getenv("DB_USER") or "postgres"
local db_pass = os.getenv("DB_PASS") or "abdu3421"
local db_host = os.getenv("DB_HOST") or "127.0.0.1"
local db_port = os.getenv("DB_PORT") or "5432"
local py_env = os.getenv("PY_ENV") or "C:/Users/Abdua/anaconda3/envs/sip_call/python.exe"
local py_path = os.getenv("PY_PATH") or "C:/Users/Abdua/Downloads/analyze/analyze_audio.py"
local default_voice

if lang == "uz" then
    default_voice = os.getenv("DEF_VOICE") or "C:/Users/Abdua/Downloads/analyze/scripts/default1.wav"
elseif lang == "ru" then
    default_voice = os.getenv("DEF_VOICE") or "C:/Users/Abdua/Downloads/analyze/scripts-ru/default1.wav"
end

-- Connect to the PostgreSQL database
local dbh = freeswitch.Dbh(string.format("postgres://%s:%s@%s:%s/robot_call", db_user, db_pass, db_host, db_port))
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
local finished = false

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
        freeswitch.msleep(100)
        new_session:execute("set", "RECORD_STEREO=true")
        new_session:execute("record_session", recording_path)
        new_session:streamFile(default_voice)

        -- Loop until finished is true
        repeat
            -- Insert audio information to database
            local response_path = "recordings/" .. UUID .. "_response.wav"
            new_session:recordFile(response_path, 7, 700, 4)
        
            local insert_audio_query = string.format([[
                INSERT INTO voicehistory (uuid, voice, scriptid, paydate, reason, calluuid, resvoice, finished)
                VALUES ('%s', '%s', %s, '', '', '%s', '', %s)]], 
                UUID, 
                response_path, 
                lang == "uz" and 0 or 10,  -- Conditional logic for script_id
                UUID, 
                false)
            freeswitch.consoleLog("INFO", insert_audio_query .. "\n")
            local success, err = dbh:query(insert_audio_query)
            if not success then
                freeswitch.consoleLog("ERROR", "Failed to insert audio information: " .. tostring(err) .. "\n")
                break -- Break the loop if the query fails
            end
            freeswitch.consoleLog("ERROR", "Language: " .. lang .. "\n")
            -- Call Python script to analyze the audio file.
            local analysis_result = os_capture(py_env .. " " .. py_path .. " " .. UUID .. " " .. lang)
            freeswitch.consoleLog("INFO", "Audio Analysis Result: " .. analysis_result .. "\n")
            
            -- Handle potential errors in audio analysis
            if not analysis_result or analysis_result == "" then
                freeswitch.consoleLog("ERROR", "Audio analysis failed or returned empty result.\n")
                break -- Break the loop if audio analysis fails
            end
        
            -- Optional: Pause for three seconds
            -- freeswitch.msleep(2000)
        
            -- Select `resvoice` and `finished` from the `voicehistory` table
            local select_audio_query = string.format([[
                SELECT resvoice, finished FROM voicehistory WHERE uuid='%s'
            ]], UUID)
        
            local resvoice
            local query_success = dbh:query(select_audio_query, function(row)
                resvoice = row.resvoice
                finished = (row.finished == 't') -- Assuming `finished` is stored as a boolean in the DB
            end)
        
            if not query_success then
                freeswitch.consoleLog("ERROR", "Failed to select resvoice: " .. tostring(err) .. "\n")
                break -- Break the loop if the select query fails
            end
            
            if resvoice and resvoice:match("%S") then
                new_session:streamFile(resvoice)
                freeswitch.consoleLog("INFO", "resvoice: " .. resvoice .. "\n")
            else
                freeswitch.consoleLog("ERROR", "No valid resvoice found or resvoice is empty/whitespace.\n")
                break -- Break the loop if `resvoice` is not found or is empty/whitespace
            end
        
            -- **Added Check: Verify if the session is still active**
            if not new_session:ready() then
                freeswitch.consoleLog("INFO", "Session is no longer active. Exiting loop.\n")
                break
            end
        
        until finished

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
