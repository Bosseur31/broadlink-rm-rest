# dependencies - falcon, wsgi server (waitress, uwsgi, etc)

import broadlink_rm_command_db
import broadlink_rm_blaster_db
import falcon
import json

## Generic helper functions

def get_blaster(attr, value):
    if (attr == "name"):
        blaster = broadlink_rm_blaster_db.get_blaster_by_name(value)
    elif (attr == "ip"):
        print value
        blaster = broadlink_rm_blaster_db.get_blaster_by_ip(value)
    elif (attr == "mac"):
        blaster = broadlink_rm_blaster_db.get_blaster_by_mac(value)
    else:
        raise falcon.HTTPNotFound(description="Invalid blaster attribute. Use attribute of name, ip, or mac for Blaster.")
    
    if blaster:
        return blaster
    else:
        raise falcon.HTTPNotFound(description="Value of '" + value + "' not found for Blaster '" + attr + "' attribute")

def get_target(target_name):
    target = broadlink_rm_command_db.get_target(target_name)

    if target:  
        return target
    else:
        raise falcon.HTTPNotFound(description="Target '" + target_name + "' not found")

def get_command(target_name, command_name):
    command = get_target(target_name).get_command(command_name)

    if command:
        return command
    else:
        raise falcon.HTTPNotFound(description="Command '" + command_name + "' not found for Target '" + target_name + "'")

## REST Server block

## Middleware Class to open and close DB properly
class MiddlewareDatabaseHandler(object):
    def process_request(self, req, resp):
        broadlink_rm_command_db.commands_db.connect()
        broadlink_rm_command_db.Command.create_table(safe=True)
        broadlink_rm_command_db.Target.create_table(safe=True)

        broadlink_rm_blaster_db.blasters_db.connect()
        broadlink_rm_blaster_db.Blaster.create_table(safe=True)
    
    def process_response(self, req, resp, resource, req_succeeded):
        broadlink_rm_command_db.commands_db.close()
        broadlink_rm_blaster_db.blasters_db.close()

# Resource to discover devices
# /discoverblasters
# GET adds all newly discovered devices to DB and returns number of new RM devices found, required when adding a new device to the network
# NOTE: Only retains devices of type RM

class DiscoverRESTResource(object):
    def on_get(self, req, resp):
        resp.body = json.dumps(broadlink_rm_blaster_db.get_new_blasters())

# Resource to interact with all discovered Blasters
# /blasters
# GET returns Blasters list
# POST sends command to all Blasters

class BlastersRESTResource(object):
    def on_get(self, req, resp):
        resp.body = json.dumps({"blasters":broadlink_rm_blaster_db.get_all_blasters_as_dict()})
    
    def on_post(self, req, resp):
        target_name = req.get_param("target_name", required=True)
        command_name = req.get_param("command_name", required=True)

        target = broadlink_rm_command_db.get_target(target_name)

        if target:
            command = target.get_command(command_name)
            if command:
                broadlink_rm_blaster_db.send_command_to_all_blasters(command)
            else:
                raise  falcon.HTTPInvalidParam("Command of '" + command_name + "' does not exist for Target '" + target_name + "'.", "command_name")

        else:
            raise falcon.HTTPInvalidParam("Target of '" + target_name + "' does not exist.", "target_name")

# Resource to return all Targets
# /targets
# GET returns all Targets

class TargetsRESTResource(object):
    def on_get(self, req, resp):
        resp.body = json.dumps({"targets":broadlink_rm_command_db.get_all_targets_as_dict()})

# Resource to return all Commands
# /commands
# GET returns all Commands

class CommandsRESTResource(object):
    def on_get(self, req, resp):
        targets = broadlink_rm_command_db.get_all_targets()
        targets_to_ret =  broadlink_rm_command_db.get_all_targets_as_dict()
        for x in range(len(targets)):
            targets_to_ret[x]["commands"] = targets[x].get_all_commands_as_dict()

        resp.body = json.dumps({"targets":targets_to_ret})

# Resource to interact with a specific Blaster
# /blasters/{attr}/{value}
# GET returns Blaster info
# PUT creates/updates Blaster name
# POST sends command to Blaster
# DELETE deletes Blaster

class BlasterRESTResource(object):
    def on_get(self, req, resp, attr, value):
        if value is None:
            raise falcon.HTTPNotAcceptable("You must specify a {value} in /blasters/{attr}/{value} to continue")

        resp.body = json.dumps(get_blaster(attr, value).to_dict())
    
    def on_put(self, req, resp, attr, value):
        new_name = req.get_param("new_name", required=True)

        if value is None:
            raise falcon.HTTPNotAcceptable("You must specify a {value} in /blasters/{attr}/{value} to continue")

        blaster = get_blaster(attr, value)

        if broadlink_rm_blaster_db.get_blaster_by_name(new_name) is None:
            blaster.put_name(new_name)
        else:
            raise falcon.HTTPConflict(description="Blaster '" + new_name + "' already exists")
    
    def on_post(self, req, resp, attr, value):
        target_name = req.get_param("target_name", required=True)
        command_name = req.get_param("command_name", required=True)

        if value is None:
            raise falcon.HTTPNotAcceptable("You must specify a {value} in /blasters/{attr}/{value} to continue")

        blaster = get_blaster(attr, value)
        target = broadlink_rm_command_db.get_target(target_name)
        
        if target:
            command = target.get_command(command_name)

            if command:
                blaster.send_command(command)
            else:
                raise falcon.HTTPNotFound(description="Command '" + command_name + "' not found for Target '" + target_name + "'")
        else:
            raise falcon.HTTPNotFound(description="Target '" + target_name + "' not found")
        
    def on_delete(self, req, resp, attr, value):
        get_blaster(attr, value).delete_instance()

# Resource to interact with a specific Target
# /targets/{target_name}
# PUT creates target
# PATCH updates target
# DELETE deletes target and associated commands

class TargetRESTResource(object):
    def on_put(self, req, resp, target_name):
        if not broadlink_rm_command_db.add_target(target_name):
            raise falcon.HTTPConflict(description="Target '" + target_name + "' already exists")
    
    def on_patch(self, req, resp, target_name):
        new_name = req.get_param("new_name", required=True)

        if broadlink_rm_command_db.get_target(new_name):
            raise falcon.HTTPConflict(description="Target '" + new_name + "' already exists")
        else:
            get_target(target_name).update_name(new_name)

    def on_delete(self, req, resp, target_name):
        if not broadlink_rm_command_db.delete_target(target_name):
            raise falcon.HTTPNotFound(description="Target '" + target_name + "' not found")

# Resource to get Target specific Commands
# /targets/{target_name}/commands
# GET returns all Commands for Target 'target_name'

class TargetCommandsRESTResource(object):
    def on_get(self, req, resp, target_name):
        target = broadlink_rm_command_db.get_target(target_name)

        if target:
            resp.body = json.dumps({"commands":target.get_all_commands_as_dict()})
        else:
            raise falcon.HTTPNotFound(description="Target '" + target_name + "' not found")

# Resource to interact with Target specific Command
# /targets/{target_name}/commands/{command_name}
# GET returns Command Value
# PUT creates/updates command - uses "value" param if exists otherwise learns command from blaster with blaster_attr/blaster_value pair
# DELETE deletes command

class TargetCommandRESTResource(object):
    def on_get(self, req, resp, target_name, command_name):
        resp.body = json.dumps(get_command(target_name, command_name).to_dict())
    
    def on_put(self, req, resp, target_name, command_name):
        value = req.get_param("value")
        blaster_attr = req.get_param("blaster_attr")
        blaster_value = req.get_param("blaster_value")

        target = get_target(target_name)

        if value:
            target.put_command(command_name, value)
        else:
            if blaster_attr is None or blaster_value is None:
                raise falcon.HTTPNotFound(description="If attempting to learn a command, you must specify blaster_attr of ip, mac, or name and corresponding blaster_value. You can also specify the IR sequence directly with the value parameter")
            else:
                blaster = get_blaster(blaster_attr, blaster_value)
                value = blaster.get_command()
                if value:
                    target.put_command(command_name, value)
                else:
                    raise falcon.HTTPGatewayTimeout(description="Blaster did not receive any IR signals to learn")
    
    def on_delete(self, req, resp, target_name, command_name):
        get_command(target_name, command_name).delete_instance()

# falcon.API instances are callable WSGI apps
app = falcon.API(middleware=MiddlewareDatabaseHandler())
app.req_options.auto_parse_form_urlencoded = True

# Resources are represented by long-lived class instances
discover = DiscoverRESTResource()
blasters = BlastersRESTResource()
blaster = BlasterRESTResource()
targets = TargetsRESTResource()
target = TargetRESTResource()
target_commands = TargetCommandsRESTResource()
target_command = TargetCommandRESTResource()
commands = CommandsRESTResource()

# All supported routes.
app.add_route('/discoverblasters', discover)
app.add_route('/blasters', blasters)
app.add_route('/targets', targets)
app.add_route('/commands', commands)
app.add_route('/blasters/{attr}/{value}', blaster)
app.add_route('/targets/{target_name}/commands/{command_name}', target_command)
app.add_route('/targets/{target_name}/commands', target_commands)
app.add_route('/targets/{target_name}', target)

# GET /discoverblasters
# GET /commands
# GET /targets
# PUT /targets/{target_name}
# DELETE /targets/{target_name}
# PATCH /targets/{target_name}?new_name={}
# GET /targets/{target_name}/commands
# GET /targets/{target_name}/commands/{command_name}
# PUT /targets/{target_name}/commands/{command_name}
# DELETE /targets/{target_name}/commands/{command_name}
# GET /blasters
# POST /blasters?target_name={}&command_name={}
# GET /blasters/{attr=name/ip/mac}/{value}
# DELETE /blasters/{attr=name/ip/mac}/{value}
# PUT /blasters/{attr=name/ip/mac}/{value}?new_name={}
# POST /blasters/{attr=name/ip/mac}/{value}?target_name={}&command_name={}