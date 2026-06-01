FROM node:22-alpine AS build
WORKDIR /app
COPY ui/package.json ui/tsconfig.json ui/vite.config.ts ui/index.html ./
COPY ui/src ./src
RUN npm install && npm run build

FROM nginx:1.27-alpine
COPY ui/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

