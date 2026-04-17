FROM node:24-alpine

RUN apk add --no-cache python3 make g++

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

RUN mkdir -p /data

EXPOSE 1883

CMD ["npx", "tsx", "src/server.ts"]
