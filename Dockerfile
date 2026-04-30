FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY orchestra.py /app/orchestra.py
COPY actions /app/actions
COPY composer_agent /app/composer_agent
COPY conductor_agent /app/conductor_agent

RUN pip install --no-cache-dir .

WORKDIR /workspace

ENTRYPOINT ["orchestra"]
