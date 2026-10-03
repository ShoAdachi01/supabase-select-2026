FROM node:22-bookworm-slim AS frontend
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
COPY public ./public
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 FORGE_DATA_DIR=/data PORT=8000
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --create-home forge && mkdir /data && chown forge /data
COPY server ./server
COPY scripts/serve.py ./scripts/serve.py
COPY --from=frontend /app/dist ./dist
USER forge
EXPOSE 8000
CMD ["python", "scripts/serve.py"]
