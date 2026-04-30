import sys
import subprocess

with open(sys.argv[1], "r") as f:
    prompt = "Create a python script from this playbook. Output ONLY valid python code, no markdown blocks:\n\n" + f.read()

res = subprocess.run(["codex", "exec", prompt], capture_output=True, text=True)

if res.returncode != 0:
    print(f"Error calling codex CLI (Return Code {res.returncode}):\n{res.stderr}")
    sys.exit(res.returncode)

with open("ip_enrichment.py", "w") as f:
    f.write(res.stdout)
