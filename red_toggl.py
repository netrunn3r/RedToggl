#!/usr/bin/env python
import requests
import sys
#import time
from pytz import timezone
import json
import datetime
#import dateutil.parser
#import optparse
import os
import configparser
from six.moves import urllib

TOGGL_URL = "https://www.toggl.com/api/v8/"

def create_empty_config():
    """
    Creates a blank ~/.redtogglrc.
    """
    cfg = configparser.ConfigParser()
    cfg.add_section('toggl')
    cfg.set('toggl', 'api_token', 'your_api_token')
    cfg.set('toggl', 'timezone', 'UTC')
    #cfg.set('toggl', 'time_format', '%I:%M%p')
    with open(os.path.expanduser('~/.redtogglrc'), 'w') as cfgfile:
        cfg.write(cfgfile)
    os.chmod(os.path.expanduser('~/.redtogglrc'), 0o600)

def get_conf_key(section, key):
    """
    Returns the value of the configuration variable identified by the
    given key within the given section of the configuration file. Raises
    ConfigParser exceptions if the section or key are invalid.
    """
    return cfg.get(section, key).strip()

def auth_toggl():
    return requests.auth.HTTPBasicAuth(get_conf_key('toggl', 'api_token'), 'api_token')

def print_toggl_data(data):
    for i in data:
        for key,val in i.items():
            print(key, ": ", val)
        print()

def get_json(req, params):
    """
    req - time_entry
    """
    return '{{"{}": {}}}'.format(req, json.dumps(params))

def get_toggl_data(url_tail, wid=0, req=None, params=None):
    """
    Get list of projects / clients / time_entries from workspace.
    To get projects, user have to be an admin
    """
    if url_tail == "projects":
        url = "{}{}".format(TOGGL_URL, "workspaces")
        r = requests.get(url, auth=auth_toggl())
        data = json.loads(r.text)
        url_tail = "workspaces/" + str(data[wid]['id']) + "/projects"

    url = "{}{}".format(TOGGL_URL, url_tail)
    #print(url)
    r = requests.get(url, auth=auth_toggl())
    #r = requests.get(url, auth=auth_toggl(), data=get_json(req, params),  headers={'content-type' : 'application/json'})
    #print(r.text)
    #print(get_json(req, params))
    return json.loads(r.text)

def get_toggl_time_entries(days):
    zone = timezone("Europe/Warsaw")
    toggl_entries = []
    projects = get_toggl_data("projects");
    clients = get_toggl_data("clients");

    for day in range(days):
        date = datetime.datetime.now(tz=zone) - datetime.timedelta(days=day)
        start_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = date.replace(hour=23, minute=59, second=59, microsecond=0)
        
        print(start_date, " - ", end_date)

        url = "time_entries?start_date={}&end_date={}".format(urllib.parse.quote(start_date.isoformat()), urllib.parse.quote(end_date.isoformat()))
        #print_toggl_data(get_toggl_data(url))
        data = get_toggl_data(url)
        for i in data:
            project = {"name": ">NO_PROJECT<"}
            client = {"name": ">NO_CLIENT<"}
            task_name = ""

            for key,val in i.items():
                if key == "pid":
                    project = find_toggl_pid(val)
                    client = find_toggl_cid(project["cid"])
                elif key == "description":
                    task_name = val
                elif key == "duration":
                    duration = str(datetime.timedelta(seconds=val))

            print("{} - {}: {} ({})". format(client["name"], project["name"], task_name, duration))

def find_toggl_pid(pid):
    projects = get_toggl_data("projects");
    found = False

    for i in projects:
        name = ">EMPTY<"
        cid = "0"

        for key,val in i.items():
            if key == "id":
                if val == pid:
                    found = True
            elif key == "name":
                name = val
            elif key == "cid":
                cid = val
        
        if found == True:
            break

    return {"name": name, "cid": cid}

def find_toggl_cid(cid):
    clients = get_toggl_data("clients");
    found = False

    if cid == 0:
        return {"name": ">EMPTY<"}


    for i in clients:
        name = ""

        for key,val in i.items():
            if key == "id":
                if val == cid:
                    found = True
            elif key == "name":
                name = val
        
        if found == True:
            break

    return {"name": name}




cfg = configparser.ConfigParser()
if cfg.read(os.path.expanduser('~/.redtogglrc')) == []:
    create_empty_config()
    raise IOError("Missing ~/.togglrc. A default has been created for editing.")

