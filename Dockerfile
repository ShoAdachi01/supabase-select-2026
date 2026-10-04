FROM node:22-bookworm-slim AS frontend
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
COPY public ./public
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 TRACE_DATA_DIR=/data CUTROOM_DATA_DIR=/data/cutroom PLAYWRIGHT_BROWSERS_PATH=/opt/browsers PORT=8000
WORKDIR /app
COPY requirements.lock ./
COPY --from=frontend /usr/local/bin/node /usr/local/bin/node
COPY --from=frontend /app/node_modules ./node_modules
RUN pip install --no-cache-dir -r requirements.lock && node node_modules/playwright/cli.js install --with-deps chromium && useradd --create-home cutroom && mkdir /data && chown cutroom /data
COPY server ./server
COPY public/sample ./public/sample
COPY scripts/serve.py scripts/video_browser.mjs scripts/video_network.mjs ./scripts/
COPY --from=frontend /app/dist ./dist
USER cutroom
EXPOSE 8000
CMD ["python", "scripts/serve.py"]
