-- Get the FreeSWITCH API
local api = freeswitch.API()

-- Specify the sip details
local uuid = argv[1]
local sip_address = argv[2]
local username = argv[3]
local password = argv[4]

-- Function to log call status and update database
local function log_status(status, dbh)
  -- Ensure `status` is a boolean value
  local status_bool = (status == "answered" and 'TRUE' or 'FALSE')
  local update_status_query = string.format("UPDATE sip SET active = %s WHERE uuid = '%s'", status_bool, uuid)
  -- Execute the query
  dbh:query(update_status_query)
  freeswitch.consoleLog("INFO", string.format("sip %s: %s\n", uuid, status))
end


-- Connect to the PostgreSQL database
local dbh = freeswitch.Dbh("postgres://postgres:abdu3421@127.0.0.1:5432/robot_call")

-- Check if the connection was successful
assert(dbh:connected(), "Failed to connect to the database")

-- Path to the sip configuration file
local sip_config_file = string.format("C:\\Program Files\\FreeSWITCH\\conf\\sip_profiles\\external\\%s.xml", uuid)

-- Create the XML snippet for the new sip
local new_sip = string.format([[
<include>
  <gateway name="%s">
    <param name="realm" value="%s"/>
    <param name="username" value="%s"/>
    <param name="password" value="%s"/>
    <param name="register" value="true"/>
  </gateway>
</include>
]], uuid, sip_address, username, password)

-- Function to write XML to file with error handling
local function write_to_file(file_path, content)
    local file, err = io.open(file_path, "w")
    if not file then
        error("Could not open file: " .. err)
    end

    local success, write_err = file:write(content)
    if not success then
        error("Could not write to file: " .. write_err)
    end

    file:close()
end

-- Function to remove a file with error handling
local function remove_file(file_path)
  local result, err = os.remove(file_path)
  if not result then
      error("Could not remove file: " .. err)
  end
end

-- Write the XML snippet to the file
write_to_file(sip_config_file, new_sip)

-- Reload the XML configuration and Sofia module
api:executeString("reloadxml")
api:executeString("reload mod_sofia")
freeswitch.consoleLog("NOTICE", "sip added and configuration reloaded.\n")

-- Check sip status
local command = string.format("sofia status gateway %s", uuid)
local reply = api:executeString(command)
freeswitch.consoleLog("INFO", "Reply: " .. reply .. "\n")

-- Check the status in the reply
local is_registered = string.find(reply, "State") and (string.find(reply, "REGED") or string.find(reply, "REGISTER"))
if is_registered then
    freeswitch.consoleLog("WARNING", "sip " .. uuid .. " is registered\n")
    log_status("answered", dbh)
else
    remove_file(sip_config_file)
    -- Reload the XML configuration and Sofia module
    api:executeString("reloadxml")
    api:executeString("reload mod_sofia")
    freeswitch.consoleLog("WARNING", "sip " .. uuid .. " is not registered\n")
    log_status("failed", dbh)
end

-- Release the database handle
dbh:release()
