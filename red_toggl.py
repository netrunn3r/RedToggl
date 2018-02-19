#!/usr/bin/env python
import requests
#import sys
from pytz import timezone
import json
import datetime
import os
import configparser
from six.moves import urllib
#import urllib3
from redminelib import Redmine
import argparse
from colorama import Fore, Style

requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
TOGGL_URL = "https://www.toggl.com/api/v8/"
#urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# switch to urllib3
# update issue in rm, when task in toggl change
# presales task
# update task, when issue done
# add comments when updating rm (in time entry and in issue)
# all issue are set to Realization - is it ok?

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

def get_conf_key(cfg, section, key):
    """
    Returns the value of the configuration variable identified by the
    given key within the given section of the configuration file. Raises
    ConfigParser exceptions if the section or key are invalid.
    """
    return cfg.get(section, key).strip()

def auth_toggl(cfg):
    return requests.auth.HTTPBasicAuth(get_conf_key(cfg, 'toggl', 'api_token'), 'api_token')

def print_toggl_data(data):
    """
    Print raw data from toggl. Debug purpose
    """
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
    cfg = get_cfg_file()
    if url_tail == "projects":
        url = "{}{}".format(TOGGL_URL, "workspaces")
        r = requests.get(url, auth=auth_toggl(cfg))
        data = json.loads(r.text)
        url_tail = "workspaces/" + str(data[wid]['id']) + "/projects"

    url = "{}{}".format(TOGGL_URL, url_tail)
    r = requests.get(url, auth=auth_toggl())
    return json.loads(r.text)

def get_toggl_time_entries(days):
    """
    Return from toggl tasks from last X days
    """
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
    """
    Find project name in toggl by its id
    """
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
    """
    Find client name in toggl by client id
    """
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
    """
    Authenticate to redmine and return Redmine object
    """
    cfg = get_cfg_file()
    url = get_conf_key(cfg, 'redmine', 'url')
    api = get_conf_key(cfg, 'redmine', 'api_token')
    ssl_verify = get_conf_key(cfg, 'redmine', 'ssl_verify') == 'True' # fix me!

    return Redmine(url, key=api, requests={'verify': ssl_verify})

def get_project_from_rm(redmine, task):
    """
    Get specific project from redmine. First try to find by project id in redmine (when named like in toggl), when nothing return then get all projects from redmine and search by name (eg. when someone change project name in redmine).
    Project name in redmine have to by 'client - project_name' in toggl.
    Return tuple with project id and time entries
    """
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
        print(Fore.RED + "There is no project '{} - {}' in Redmine. Contact PM to create one or assign to you.".format(task["client"], task["project"]) + Style.RESET_ALL)
        return (-1, -1)   # no project

    return (project["id"], project["time_entry_activities"])

def get_issue_from_rm(redmine, task, project_id):
    """
    Get issue from redmine and return its id
    """
    issues = redmine.issue.filter(project_id=project_id, status_id='*')
    for issue in issues:
        if issue["subject"] == task["name"]:
            return issue["id"]

    print(Fore.YELLOW + "There is no issue '{}' in project '{} - {}' - adding new one".format(task["name"], task["client"], task["project"]) + Style.RESET_ALL)
    return -2   # no issue

def new_issue(redmine, task, project_id):
    """
    Create new issue in redmine and return its id
    """
    status_id = get_status_id(redmine, "Realization")
    my_id = redmine.user.get("current")["id"]
#    issue = redmine.issue.create(
#            project_id=project_id,
#            subject=task["name"],
#            status_id=status_id,
#            assigned_to_id=my_id)
### TEMPORARY HACK! ###
# for now, we have one project where we have to choose salesperson
# we are working on presales module, which will handle creating presales tasks
    issue = redmine.issue.new()
    issue.project_id = project_id
    issue.subject=task["name"]
    issue.status_id=status_id
    issue.assigned_to_id=my_id
    if project_id == 93:        ## Presales tasks's
        ss = ""
        for tag in task["tags"]:
            if tag != "Preparing an offer": # hope that there will be no other tags than 
                ss = tag
                break                       # salesperson and 'preparing an offer'
        if not ss:
            print(Fore.RED + "No salesperson in task '{}'".format(task["name"]) + Style.RESET_ALL)
            return -100     # no salesperson
        issue.custom_fields = [{'id': 9, 'name': 'Salesperson', 'value': ss}]
        print("    Salesperson: {}".format(ss))

    issue.save()
### END HACK ###

#    print("Added new issue:")
#    for key,val in issue:
#        print("{}: {}".format(key, val))

    print("\
    Issue ID: {}\n\
    Subject: {}\n\
    Project ID: {} ({})\n\
    Tracker ID: {} ({})\n\
    Status ID: {} ({})\n\
    Priority ID: {} ({})\n\
    Author ID: {} ({})\n\
    Assigned to ID: {} ({})"\
    .format(
        issue["id"],
        issue["subject"],
        issue["project"]["id"], issue["project"]["name"],
        issue["tracker"]["id"], issue["tracker"]["name"],
        issue["status"]["id"], issue["status"]["name"],
        issue["priority"]["id"], issue["priority"]["name"],
        issue["author"]["id"], issue["author"]["name"],
        issue["assigned_to"]["id"], issue["assigned_to"]["name"]))



    return issue["id"]

def get_status_id(redmine, status_name):
    """
    Return issue status id by issue status name.
    Issue status name for example can be "New", "Realization", "Done", "Cancelled"

    """
    statuses = redmine.issue_status.all()
    for status in statuses:
        if status_name == status["name"]:
            return status["id"]
    print(Fore.YELLOW  + "There is no issue status like '{}'. Setting no value for this field".format(status_name) + Style.RESET_ALL)
    return None   # no issue_status
    
def get_activity(task, project_activities):
    """
    Find in toggl tags, project activities from redmine. 
    Creating new time entry in redmine, we have to choose time_entry_activities (which are global in project, so we can call them project_activities). In toggl we choose by taking proper tag.
    Return matching redmine time_entry_activities / toggl tag
    """
    if not task["tags"]:
        print(Fore.RED + "There is no tags in toggl, please correct it in task '{}' ({} -> {})".format(task["name"], task["project"], task["client"]) + Style.RESET_ALL)
        return (-3, -3)   # no activity in toggl

    for activity in project_activities:
        if activity["name"] in task["tags"]:
            return (activity["id"], activity["name"])

    print(Fore.RED + "There is no '{}' activity in Redmine, please correct it".format(task["tags"]) + Style.RESET_ALL)
    return (-4, -4)   # no activity in rm

def get_authors_from_toggl(task):
    """
    In *OUR* redmine, we have custom field 'Praca autorska'. We are checking if there is 'Autorska' tag in toggl, if so we set 'Praca autorska' in redmine during creating new issue.
    Return exact value to pass to custom field in redmine
    """
    if "Autorska" in task["tags"]:
        return [{'id': 1, 'name': 'Praca autorska', 'value': '1'}]
    else:
        return [{'id': 1, 'name': 'Praca autorska', 'value': '0'}]
    
def parse_date(date_str): # we have 2018-01-30T08:27:28+00:00
    """
    Parse date to match format in redmine. Creating from scratch to be sure that it is correct
    """
    date_splited = date_str.split('+')
    date_splited[1] = date_splited[1].replace(':', '')
    date_joined = '+'.join(date_splited)
    date = datetime.datetime.strptime(date_joined, "%Y-%m-%dT%H:%M:%S%z")

    return date.date() # return only date

def print_time_entry(te, activity_name, task_name):
    """
    Print redmine time entry
    """
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
    """
    When inserting new time entry from toggl, check if it already exist. We compare value in comment if it is the same as toggl task id.
    Return >=0 when there is no time entry and <0 if it already is
    """
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
    """
    Create new time entry in redmine and put in comment toggl task id by which we will check if time entry was already created or not
    """
    (project_id, project_activities) = get_project_from_rm(redmine, task)
    if project_id < 0:
        return 

    (activity_id, activity_name) = get_activity(task, project_activities)
    if activity_id < 0:
        return

    issue_id = get_issue_from_rm(redmine, task, project_id)
    if issue_id < 0:
        issue_id = new_issue(redmine, task, project_id)

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

def get_cfg_file():
    """
    Create empty config file if it not exist. If present, read it and return ConfigParser object
    """
    cfg = configparser.ConfigParser()
    if cfg.read(os.path.expanduser('~/.redtogglrc')) == []:
        create_empty_config()
        raise IOError("Missing ~/.togglrc. A default has been created for editing.")
    return cfg


def main(args):
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


# notes:
#issues = redmine.issue.filter(project_id='parp-testy-penetracyjne-sieci', status_id='*')
#for i in issues:
#    print(i.subject)

#issues[4].subject
#list(issues[4])
#list(redmine.issue.get(112))
