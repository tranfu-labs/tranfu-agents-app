FROM python:3.12-slim
WORKDIR /app
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server ./server
COPY dashboard ./dashboard
ENV TF_DB=/data/tf.db PORT=8788
VOLUME /data
EXPOSE 8788
CMD ["python","-m","uvicorn","server.app:app","--host","0.0.0.0","--port","8788"]
