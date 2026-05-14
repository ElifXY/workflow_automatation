FROM node:20-alpine AS builder
WORKDIR /app
ARG REACT_APP_API_URL=/api
ENV REACT_APP_API_URL=$REACT_APP_API_URL
COPY package*.json ./
RUN npm install --silent
COPY . .
RUN npm run build

FROM nginx:1.25-alpine
RUN apk add --no-cache wget
COPY --from=builder /app/build /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
