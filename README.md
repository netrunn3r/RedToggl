# RedToggl
## Integration between Redmine and Toggl
RedToggl is a tool wich send tasks from toggl to on-premise redmine instance. It can create new issue and assign time log to them in redmine, based on toggl tasks and tags.
  
## Features
* work with toggl api v8
* work with redmine version 3.4.4
* read task's tags in toggl and create specific issue activity
* work with custom fields in redmine issue
* sync X last days

## Instalation
Just install modules from requirements.txt

## Preparation
For now, we have to create manually projects and clients in toggl. In redmine, projects have to be create in schema: "Client name - Project name". Based on that, RedToggl will match projects in toggl and in redmine.
For creating new log time in redmine we normaly have to choose time entry activity. That time entry have to be created in toggl tags.

## First run and configuration
When RedToggl is run for the first time it create config file in ~/.redtogglrc. In that file you have to put api keys from toggl and redmine. Additionally you have to put there your redmine address.

## *OUR* customization
I create this tool for myself to work on toggl tasks, not in redmine log times which is our company main tool to log our work time. We have some customization which you can find in code:
1. All new issues are created with "Realization" status
2. We have custom field 'Autorska' in issue - when in toggl task there is tag 'Autorska', we set this custom field in redmine to 'true'

## How it work
1. Get tasks from toggl from last X days
2. For each task from 1. check in redmine:
    1. that project exist, if not throw an error - Project Manager have to add new project
    2. that issue exists, if not create new one
    3. that log time in issue exists, if not create new one and **write to comment task id from toggl**
    4. if there is log time in issue, check task id from toggl in redmine log time comment:
        1. if there is log time with id in comment like task id in toggl, do nothing - this task was sync previously
        2. if there is no log time with id in comment like task id in toggl, create new log time - this task wasn't sync previously

## Usage
```
$ ./red_toggl.py -h
usage: red_toggl.py [-h] days

positional arguments:
  days        How many days sync with Redmine

optional arguments:
  -h, --help  show this help message and exit
  ```
