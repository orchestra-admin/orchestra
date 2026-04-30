#!/usr/bin/env python3
import argparse
import sys
from composer_agent.composer import compose_script
from conductor_agent.conductor import (
    init_project, print_actions, print_integrations,
    print_playbooks, activate_playbook, deactivate_playbook, run_playbook,
    list_schedules, add_schedule, remove_schedule, run_scheduler,
    run_musician, start_server, review_playbook,
)

def main():
    parser = argparse.ArgumentParser(description="Orchestra SOAR CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    gen_parser = subparsers.add_parser("compose", help="Compose a Python script from a playbook")
    gen_parser.add_argument("playbook", help="Path to the playbook markdown file")

    subparsers.add_parser("init", help="Initialize an Orchestra automation project")
    
    subparsers.add_parser("actions", help="List available actions and update the index")

    subparsers.add_parser("integrations", help="List available integrations and update the index")

    playbook_parser = subparsers.add_parser("playbook", help="Manage playbooks (list, activate, deactivate)")
    playbook_sub = playbook_parser.add_subparsers(dest="playbook_action", required=True)
    playbook_sub.add_parser("list", help="List all available playbooks")
    activate_parser = playbook_sub.add_parser("activate", help="Activate a playbook")
    activate_parser.add_argument("event_type", help="Event type of the playbook to activate")
    deactivate_parser = playbook_sub.add_parser("deactivate", help="Deactivate a playbook")
    deactivate_parser.add_argument("event_type", help="Event type of the playbook to deactivate")
    run_parser = playbook_sub.add_parser("run", help="Run a playbook manually")
    run_parser.add_argument("event_type", help="Event type of the playbook to run")
    run_parser.add_argument("--payload", default="{}", help="JSON payload string")

    review_parser = playbook_sub.add_parser("review", help="Review a playbook and provide feedback")
    review_parser.add_argument("playbook", help="Path to the playbook markdown file")

    server_parser = subparsers.add_parser("server", help="Start the webhook server")
    server_parser.add_argument("--port", type=int, default=8080, help="Port to listen on")

    subparsers.add_parser("musician", help="Start the local Redis musician")

    schedule_parser = subparsers.add_parser("schedule", help="Manage playbook schedules (list, add, remove)")
    schedule_sub = schedule_parser.add_subparsers(dest="schedule_action", required=True)
    schedule_sub.add_parser("list", help="List all scheduled playbooks")
    add_parser = schedule_sub.add_parser("add", help="Add or update a schedule")
    add_parser.add_argument("event_type", help="Event type of the playbook")
    add_parser.add_argument("cron", help="Cron expression (5 fields, quoted)")
    rm_parser = schedule_sub.add_parser("remove", help="Remove a schedule")
    rm_parser.add_argument("event_type", help="Event type of the playbook")

    subparsers.add_parser("scheduler", help="Start the schedule-based trigger process")
    
    args = parser.parse_args()
    
    if args.command == "compose":
        compose_script(args.playbook)
    elif args.command == "init":
        init_project()
    elif args.command == "actions":
        print_actions()
    elif args.command == "integrations":
        print_integrations()
    elif args.command == "playbook":
        if args.playbook_action == "list":
            print_playbooks()
        elif args.playbook_action == "activate":
            activate_playbook(args.event_type)
        elif args.playbook_action == "deactivate":
            deactivate_playbook(args.event_type)
        elif args.playbook_action == "run":
            import json
            try:
                payload = json.loads(args.payload)
            except json.JSONDecodeError:
                print("Error: --payload must be valid JSON.", file=sys.stderr)
                sys.exit(1)
            run_playbook(args.event_type, payload)
        elif args.playbook_action == "review":
            review_playbook(args.playbook)
    elif args.command == "server":
        try:
            start_server(args.port)
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "musician":
        try:
            exit_code = run_musician()
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

        sys.exit(exit_code)
    elif args.command == "schedule":
        if args.schedule_action == "list":
            list_schedules()
        elif args.schedule_action == "add":
            add_schedule(args.event_type, args.cron)
        elif args.schedule_action == "remove":
            remove_schedule(args.event_type)
    elif args.command == "scheduler":
        try:
            run_scheduler()
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
