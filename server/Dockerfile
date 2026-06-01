FROM python:3.12-slim
WORKDIR /app
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server ./server
COPY dashboard ./dashboard
COPY install.sh ./install.sh
ENV TF_DB=/data/tf.db PORT=8787
VOLUME /data
EXPOSE 8787
CMD ["python","-m","uvicorn","server.app:app","--host","0.0.0.0","--port","8787"]
