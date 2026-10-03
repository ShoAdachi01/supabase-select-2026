FROM node:22-bookworm-slim AS frontend
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
COPY public ./public
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 TRACE_DATA_DIR=/data PORT=8000
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --create-home trace && mkdir /data && chown trace /data
COPY server ./server
COPY public/demo ./public/demo
COPY scripts/serve.py ./scripts/serve.py
COPY --from=frontend /app/dist ./dist
USER trace
EXPOSE 8000
CMD ["python", "scripts/serve.py"]
