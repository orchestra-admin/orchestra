# Orchestra MVP Spec

Create an MVP for a CLI tool that turns plain-English playbooks into runnable Python scripts.

## Files

```
orchestra/
├── .agents/
│   ├── AGENT.md
│   └── specs/
│       └── SPEC_v1.md
├── generate.py         # the CLI tool
└── ip_enrichment.md
|-- ip_enrichment.py
```

## Usage

```bash
python generate.py ip_enrichment.md
# write the generated script to ip_enrichment.py
```

## How generate.py Works

1. Read the playbook file
2. Call the local gemini cli tool to convert playbook to python script.
3. Write the response to ip_enrichment.py

## Playbook Format

```markdown
# Playbook: IP Enrichment

Quick summary that introduce what the playbook does. Input/Output format and what tools to use. 


## Steps
1. Some step
2. Some more steps
3. etc etc

## Environment Variables
- SOME_API_KEY
- OTHER_USEFUL_VARIABLES
```


## Not In Scope
- Error handling
- Any integrations beyond VT + Slack
