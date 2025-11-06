FROM python:3.12-alpine

WORKDIR /app

COPY index.html /app/
COPY serve.py /app/

EXPOSE 5500

CMD ["python3", "serve.py"]
