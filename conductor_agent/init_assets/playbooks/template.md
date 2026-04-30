# Playbook: <Human-readable name>

Playbooks are markdown files with a fixed structure. It will be read by the composer to generate the scripts.

All sections are heavily recommended but not required.

## Description
Detailed description of this playbook, what is it for, when should it be used, what is the expected input/output etc.

## Inputs
- Descript the inputs format of the playbook

## Invocation
Describe ways the playbook can be invoked. (e.g. This playbook is invoked by a webhook `POST` to `/webhook` with `event_type` in the JSON payload.)

## Steps
1. Plain English description of step one
2. Plain English description of step two
3. For more precised output, you should explicitly reference library actions in your step.

## Output
- What should the program do after the steps are completed?
    e.g. Send the output to Slack <channel-name> when in some specific format

## Environment Variables
- `ENV_VAR_NAME`: What it is and where to get it
