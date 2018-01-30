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
from redminelib import Redmine
import argparse
from colorama import Fore, Style

TOGGL_URL = "https://www.toggl.com/api/v8/"
cfg = configparser.ConfigParser()

def create_empty_config():
    """
    Creates a blank ~/.redtogglrc.
    """
    cfg = configparser.ConfigParser()
    cfg.add_section('toggl')
    cfg.set('toggl', 'api_token', 'your_api_token')
    cfg.set('toggl', 'timezone', 'UTC')
    #cfg.set('toggl', 'time_format', '%I:%M%p')
    cfg.add_section('redmine')
    cfg.set('redmine', 'api_token', 'your_api_token')
    cfg.set('redmine', 'url', 'https://your_redmine.com')
    cfg.set('redmine', 'ssl_verify', 'False')
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
    r = requests.get(url, auth=auth_toggl())
    return json.loads(r.text)

def get_toggl_time_entries(days):
    zone = timezone("Europe/Warsaw")
    toggl_entries = []
    projects = get_toggl_data("projects")
    clients = get_toggl_data("clients")
    tasks = []

    for day in range(days):
        date = datetime.datetime.now(tz=zone) - datetime.timedelta(days=day)
        start_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = date.replace(hour=23, minute=59, second=59, microsecond=0)
        
        print(Fore.YELLOW + str(start_date.date()) + Style.RESET_ALL)

        url = "time_entries?start_date={}&end_date={}".format(urllib.parse.quote(start_date.isoformat()), urllib.parse.quote(end_date.isoformat()))
        data = get_toggl_data(url)
        for i in data:
            project = {"name": ">NO_PROJECT<"}
            client = {"name": ">NO_CLIENT<"}
            name = ""
            id = ""
            tags = ""
            start = ""
            hours = 0.0

            for key,val in i.items():
                #print("{}: {}".format(key,val))
                if key == "pid":
                    project = find_toggl_pid(val)
                    client = find_toggl_cid(project["cid"])
                elif key == "description":
                    name = val
                elif key == "duration":
                    duration = str(datetime.timedelta(seconds=val))
                    hours = round(float(val)/3600, 2)
                elif key == "id":
                    id = val
                elif key == "tags":
                    tags = val
                elif key == "start":
                    start = val

            print("{} - {}: {} ({})". format(client["name"], project["name"], name, duration))
            tasks.append({"client": client["name"], "project": project["name"], "name": name, "duration": duration, "id": id, "tags": tags, "start": start, "hours": hours})

    return tasks

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

def auth_redmine():
    url = get_conf_key('redmine', 'url')
    api = get_conf_key('redmine', 'api_token')
    ssl_verify = get_conf_key('redmine', 'ssl_verify') == 'True' # fix me!

    return Redmine(url, key=api, requests={'verify': ssl_verify})

def get_project_from_rm(redmine, task):
    fast_project_name_rm = task["client"] + "-" + task["project"]
    fast_project_identifier_rm = fast_project_name_rm.replace(" ", "-").lower()
    project_name_rm = (task["client"] + " - " + task["project"]).lower()
    
    try: # try fast lookup - work if project was create with good name schema
        project = redmine.project.get(fast_project_identifier_rm, include="time_entry_activities")
    except: # if not, search in all projects
        projects = redmine.project.all(include="time_entry_activities")
        for project in projects:
            if project["name"].lower() == project_name_rm:
                return (project["id"], project["time_entry_activities"])
        # if no project founded, return error    
        print("There is no project '{} - {}' in Redmine. Contact PM to create one or assign to you.".format(task["client"], task["project"]))
        return (-1, -1)   # no project

    return (project["id"], project["time_entry_activities"])

def get_issue_from_rm(redmine, task, project_id):
    issues = redmine.issue.filter(project_id=project_id, status_id='*')
    for issue in issues:
        if issue["subject"] == task["name"]:
            return issue["id"]

    print("There is no issue '{}' in project '{} - {}' - adding new one".format(task["name"], task["client"], task["name"]))
    return -2   # no issue

def new_issue(redmine, task_name, project_id):
    status_id = get_status_id(redmine, "Realization")
    my_id = redmine.user.get("current")["id"]
    issue = redmine.issue.create(
            project_id=project_id,
            subject=task_name,
            status_id=status_id,
            assigned_to_id=my_id)

    print("Added new issue:")
    for key,val in issue:
        print("{}: {}".format(key, val))

    return issue["id"]

def get_status_id(redmine, status_name):
    statuses = redmine.issue_status.all()
    for status in statuses:
        if status_name == status["name"]:
            return status["id"]
    print("There is no issue status like '{}'. Setting no value for this field".format(status_name))
    return None   # no issue_status
    
def get_activity(task, project_activities):
    if not task["tags"]:
        print("There is no tags in toggl, please correct it in task '{}' ({} -> {})".format(task["name"], task["project"], task["client"]))
        return (-3, -3)   # no activity in toggl

    for activity in project_activities:
        if activity["name"] in task["tags"]:
            return (activity["id"], activity["name"])

    print("There is no '{}' activity in Redmine, please correct it".format(task["tags"]))
    return (-4, -4)   # no activity in rm

def get_authors_from_toggl(task):
    if "Autorska" in task["tags"]:
        return [{'id': 1, 'name': 'Praca autorska', 'value': '1'}]
    else:
        return [{'id': 1, 'name': 'Praca autorska', 'value': '0'}]
    
def parse_date(date_str): # we have 2018-01-30T08:27:28+00:00
    date_splited = date_str.split('+')
    date_splited[1] = date_splited[1].replace(':', '')
    date_joined = '+'.join(date_splited)
    date = datetime.datetime.strptime(date_joined, "%Y-%m-%dT%H:%M:%S%z")

    return date.date() # return only date

def print_time_entry(te, activity_name, task_name):
    print("\
    Issue ID: {} ({})\n\
    Spent on: {}\n\
    Hours: {}\n\
    Activity ID: {} ({})\n\
    Comments: {}\n\
    Custom fields: {}"\
    .format(
        te["issue"], task_name,
        te["spent_on"], 
        te["hours"], 
        te["activity"], activity_name,
        te["comments"], 
        list(te["custom_fields"][0])))


def check_time_entry_exist(redmine, task, issue_id, activity_name):
    time_entries = redmine.time_entry.filter(
            issue_id=issue_id,
            spent_on=parse_date(task["start"]),
            user_id=redmine.user.get("current")["id"],
            hours=str(task["hours"]))

    if not time_entries:
        return 0   # no candidates for time entry

    for time_entry in time_entries:
        time_entry_id = time_entry["comments"].split(" ")[1]
        if str(time_entry_id) == str(task["id"]): # to big to compare as int (785514187)
            print(Fore.RED + "Time entry exist:" + Style.RESET_ALL)
            print_time_entry(time_entry, activity_name, task["name"])
            return -6   # time entry exist

    return 1    # no time entry with our id


def create_time_entry_in_rm(redmine, task):
    (project_id, project_activities) = get_project_from_rm(redmine, task)
    if project_id < 0:
        return 

    (activity_id, activity_name) = get_activity(task, project_activities)
    if activity_id < 0:
        return

    issue_id = get_issue_from_rm(redmine, task, project_id)
    if issue_id < 0:
        issue_id = new_issue(redmine, task["name"], project_id)

    spent_on = parse_date(task["start"])
    hours = task["hours"]
    comments = "Id: " + str(task["id"]) + " (created by RedToggl)"
    custom_fields = get_authors_from_toggl(task)

    if check_time_entry_exist(redmine, task, issue_id, activity_name) < 0:
        return

    time_entry = redmine.time_entry.create(
            issue_id = issue_id, 
            spent_on = spent_on,
            hours = hours,
            activity_id = activity_id,
            comments = comments,
            custom_fields = custom_fields)
    print(Fore.GREEN + "Adding new time entry:" + Style.RESET_ALL)
    print_time_entry(time_entry, activity_name, task["name"])

def main(args):
    if cfg.read(os.path.expanduser('~/.redtogglrc')) == []:
        create_empty_config()
        raise IOError("Missing ~/.togglrc. A default has been created for editing.")

    redmine = auth_redmine()
    print(Fore.MAGENTA + ("=> Getting tasks from toggl").upper() + Style.RESET_ALL)
    tasks = get_toggl_time_entries(args.days)
    print(Fore.MAGENTA + ("=> Synchronizing tasks with Redmine").upper() + Style.RESET_ALL)
    for task in tasks:
        create_time_entry_in_rm(redmine, task)
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("days", help="How many days sync with Redmine", type=int)
    args = parser.parse_args()
    main(args)



#0. sprawdz jakim jestes userem [ user = redmine.user.get('current') ]
#1. sprawdz czy istnieje projekt
#2. jesli tak, wyszukaj issue, jak nie zwroc blad
#3. jesli ejst issue, sprawdz czy jest odowiedni log time, jesli nie dodaj issue i czas
#4. jesli jest log time, idz dalej, jak nie ma to dodaj i idz dalej

#issues = redmine.issue.filter(project_id='parp-testy-penetracyjne-sieci', status_id='*')
#for i in issues:
#    print(i.subject)

#issues[4].subject
#list(issues[4])
#list(redmine.issue.get(112))
# update 

