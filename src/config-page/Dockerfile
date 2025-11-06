FROM nginx:alpine

WORKDIR /app

COPY src/config-page/index.html /app/
COPY src/config-page/nginx.conf /etc/nginx/nginx.conf

RUN mkdir -p /run/nginx /var/log/nginx

EXPOSE 5500 8888

CMD ["nginx", "-g", "daemon off;"]
