import sys
from pathlib import Path

from conductor_agent.conductor_tasks.llm import llm_query


def compose_script(playbook_path, output_path=None):
    project_root = Path.cwd()
    playbook_path = Path(playbook_path)
    musicsheets_dir = project_root / "musicsheets"

    if not musicsheets_dir.is_dir():
        print(
            "Error: musicsheets/ not found in current directory. "
            "Run this command from an initialized Orchestra project.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not output_path:
        output_path = musicsheets_dir / f"{playbook_path.stem}.py"
    else:
        output_path = Path(output_path)
    
    with open(playbook_path, "r") as f:
        playbook_text = f.read()
        
    prompt_path = Path(__file__).parent / "composer.md"
    with open(prompt_path, "r") as f:
        system_prompt = f.read()

    user_message = f"Here is the playbook to convert: {playbook_text}. Generate the Python script now."
    prompt = system_prompt + "\n\n" + user_message
    
    print(f"[*] Composing script for {playbook_path}...")
    code_output = llm_query(prompt)
        
    with open(output_path, "w") as f:
        f.write(code_output)
        
    print(f"[+] Output written to {output_path}")
