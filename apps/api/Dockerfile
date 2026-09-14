FROM python:3.12-slim
WORKDIR /srv/api
COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/api/ .
RUN pip install --no-cache-dir --no-deps .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
