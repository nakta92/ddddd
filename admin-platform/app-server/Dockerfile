FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install --omit=dev

COPY src ./src

ENV NODE_ENV=production \
    WS_PORT=50066 \
    REST_PORT=50067

EXPOSE 50066 50067

CMD ["node", "src/index.js"]
