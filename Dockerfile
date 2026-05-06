FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir flask flask-cors

# 把你已有的 dget 可执行文件（Linux 二进制）放在同目录，构建时复制进容器
COPY dget /usr/local/bin/dget
RUN chmod +x /usr/local/bin/dget

COPY server.py .
COPY static/ ./static/

RUN mkdir -p /downloads /app/data

ENV DOWNLOAD_DIR=/downloads
ENV DATA_DIR=/app/data
ENV PORT=8080
ENV DGET_USER=admin
ENV DGET_PASS=admin123

EXPOSE 8080

CMD ["python", "-u", "server.py"]
